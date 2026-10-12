"""Scientific tables matching the existing DAHLIA SQL Server physical model.

Importing this module registers mappings only; it never changes the database.
Dataset row_index is the zero-based CSV row position used by the frontend,
not the CSV's Id column. Central storage contains completed experiments only.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from app.db.base_class import Base


class _DatabaseUtcNow(FunctionElement):
    type = sa.DateTime()
    inherit_cache = True


@compiles(_DatabaseUtcNow)
def _compile_utc_default(element, compiler, **kw):
    return 'CURRENT_TIMESTAMP'


@compiles(_DatabaseUtcNow, 'mssql')
def _compile_utc_mssql(element, compiler, **kw):
    return 'SYSUTCDATETIME()'


def _utcnow() -> datetime:
    # DATETIME2 stores UTC without an offset, as required by the SQL scripts.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _identity():
    return mapped_column(sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
                         primary_key=True, autoincrement=True)


def _timestamp():
    return sa.DateTime().with_variant(mssql.DATETIME2(precision=3), 'mssql')


def _json_check(column: str, name: str):
    # The existing SQL Server checks use ISJSON, unavailable in SQLite tests.
    return sa.CheckConstraint(f'ISJSON({column}) = 1', name=name).ddl_if(dialect='mssql')


def _nonempty_check(column: str, name: str):
    return sa.CheckConstraint(f'LEN(LTRIM(RTRIM({column}))) > 0', name=name).ddl_if(dialect='mssql')


class Dataset(Base):
    __tablename__ = 'dataset'
    __table_args__ = (
        sa.UniqueConstraint('name', name='UQ_dataset_name'),
        _nonempty_check('name', 'CK_dataset_name_not_empty'),
        _nonempty_check('csv_file_name', 'CK_dataset_file_name_not_empty'),
        sa.CheckConstraint('row_count > 0', name='CK_dataset_row_count'),
        sa.CheckConstraint('precision_value > 0', name='CK_dataset_precision'),
        _json_check('reference_columns_json', 'CK_dataset_reference_columns_json'),
        _json_check('categorical_columns_json', 'CK_dataset_categorical_columns_json'),
        {'schema': 'dahlia'},
    )
    dataset_id: Mapped[int] = _identity()
    name: Mapped[str] = mapped_column(sa.Unicode(128))
    description: Mapped[str | None] = mapped_column(sa.Unicode(1000))
    csv_file_name: Mapped[str] = mapped_column(sa.Unicode(260))
    csv_file: Mapped[bytes] = mapped_column(sa.LargeBinary().with_variant(mssql.VARBINARY(), 'mssql'))
    csv_sha256: Mapped[bytes] = mapped_column(sa.LargeBinary(32).with_variant(mssql.BINARY(32), 'mssql'))
    row_count: Mapped[int] = mapped_column(sa.Integer)
    imputed_column: Mapped[str] = mapped_column(sa.Unicode(128))
    target_column: Mapped[str | None] = mapped_column(sa.Unicode(128))
    reference_columns_json: Mapped[str] = mapped_column(sa.UnicodeText().with_variant(mssql.NVARCHAR(), 'mssql'))
    categorical_columns_json: Mapped[str] = mapped_column(sa.UnicodeText().with_variant(mssql.NVARCHAR(), 'mssql'), default='[]')
    precision_value: Mapped[Decimal] = mapped_column(sa.Numeric(18, 8))
    created_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.app_user.user_id'))
    created_at: Mapped[datetime] = mapped_column(_timestamp(), default=_utcnow)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class PredefinedSet(Base):
    __tablename__ = 'predefined_set'
    __table_args__ = (
        sa.UniqueConstraint('dataset_id', 'name', name='UQ_predefined_set_dataset_name'),
        _nonempty_check('name', 'CK_predefined_set_name'),
        sa.UniqueConstraint('predefined_set_id', 'dataset_id', 'na_fraction', name='UQ_predefined_set_identity'),
        sa.CheckConstraint('na_fraction > 0 AND na_fraction < 1', name='CK_predefined_set_na_fraction'),
        {'schema': 'dahlia'},
    )
    predefined_set_id: Mapped[int] = _identity()
    name: Mapped[str] = mapped_column(sa.Unicode(128))
    dataset_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.dataset.dataset_id'))
    na_fraction: Mapped[Decimal] = mapped_column(sa.Numeric(9, 6))
    created_by: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.app_user.user_id'))
    created_at: Mapped[datetime] = mapped_column(_timestamp(), default=_utcnow)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class PredefinedSetPoint(Base):
    __tablename__ = 'predefined_set_point'
    __table_args__ = (
        sa.CheckConstraint('row_index >= 0', name='CK_predefined_set_point_row_index'),
        sa.CheckConstraint('annotation_order IS NULL OR annotation_order BETWEEN 1 AND 15', name='CK_predefined_set_point_annotation_order'),
        {'schema': 'dahlia'},
    )
    predefined_set_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.predefined_set.predefined_set_id'), primary_key=True)
    row_index: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    annotation_order: Mapped[int | None] = mapped_column(sa.SmallInteger)


class Experiment(Base):
    __tablename__ = 'experiment'
    __table_args__ = (
        sa.UniqueConstraint('experiment_uid', name='UQ_experiment_uid'),
        _nonempty_check('app_version', 'CK_experiment_app_version'),
        sa.CheckConstraint('payload_json IS NULL OR ISJSON(payload_json) = 1',
                           name='CK_experiment_payload_json').ddl_if(dialect='mssql'),
        sa.ForeignKeyConstraint(
            ['predefined_set_id', 'dataset_id', 'na_fraction'],
            ['dahlia.predefined_set.predefined_set_id', 'dahlia.predefined_set.dataset_id', 'dahlia.predefined_set.na_fraction'],
            name='FK_experiment_predefined_set',
        ),
        sa.CheckConstraint(
            "(source_type = 'SEEDED' AND seed IS NOT NULL AND predefined_set_id IS NULL) OR "
            "(source_type = 'PREDEFINED' AND seed IS NULL AND predefined_set_id IS NOT NULL)",
            name='CK_experiment_source',
        ),
        sa.CheckConstraint('seed IS NULL OR seed >= 0', name='CK_experiment_seed'),
        sa.CheckConstraint('na_fraction > 0 AND na_fraction < 1', name='CK_experiment_na_fraction'),
        sa.CheckConstraint("projection IN ('pca', 'tsne', 'umap')", name='CK_experiment_projection'),
        {'schema': 'dahlia'},
    )
    experiment_id: Mapped[int] = _identity()
    experiment_uid: Mapped[UUID] = mapped_column(sa.Uuid(as_uuid=True))
    annotator_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.app_user.user_id'))
    dataset_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.dataset.dataset_id'))
    source_type: Mapped[str] = mapped_column(sa.Unicode(16))
    seed: Mapped[int | None] = mapped_column(sa.BigInteger)
    predefined_set_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    na_fraction: Mapped[Decimal] = mapped_column(sa.Numeric(9, 6))
    projection: Mapped[str] = mapped_column(sa.Unicode(32))
    completed_at: Mapped[datetime] = mapped_column(_timestamp())
    synced_at: Mapped[datetime] = mapped_column(_timestamp(), server_default=_DatabaseUtcNow())
    app_version: Mapped[str] = mapped_column(sa.Unicode(32))
    payload_json: Mapped[str | None] = mapped_column(sa.UnicodeText().with_variant(mssql.NVARCHAR(), 'mssql'))
    payload_sha256: Mapped[bytes | None] = mapped_column(sa.LargeBinary(32).with_variant(mssql.BINARY(32), 'mssql'))


class ExperimentPoint(Base):
    __tablename__ = 'experiment_point'
    __table_args__ = (
        sa.UniqueConstraint('experiment_id', 'row_index', name='UQ_experiment_point_row'),
        sa.CheckConstraint('row_index >= 0', name='CK_experiment_point_row_index'),
        sa.CheckConstraint('annotation_order IS NULL OR annotation_order BETWEEN 1 AND 15', name='CK_experiment_point_annotation_order'),
        {'schema': 'dahlia'},
    )
    experiment_point_id: Mapped[int] = _identity()
    experiment_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.experiment.experiment_id'))
    row_index: Mapped[int] = mapped_column(sa.Integer)
    annotation_order: Mapped[int | None] = mapped_column(sa.SmallInteger)
    true_value: Mapped[float] = mapped_column(sa.Float(53))


class PointPrediction(Base):
    __tablename__ = 'point_prediction'
    __table_args__ = (
        sa.UniqueConstraint('experiment_point_id', 'predictor_type', 'predictor_name', name='UQ_point_prediction'),
        _nonempty_check('predictor_name', 'CK_point_prediction_name'),
        sa.CheckConstraint("predictor_type IN ('ANNOTATOR', 'METHOD')", name='CK_point_prediction_type'),
        {'schema': 'dahlia'},
    )
    point_prediction_id: Mapped[int] = _identity()
    experiment_point_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.experiment_point.experiment_point_id'))
    predictor_type: Mapped[str] = mapped_column(sa.Unicode(16))
    predictor_name: Mapped[str] = mapped_column(sa.Unicode(128))
    predicted_value: Mapped[float] = mapped_column(sa.Float(53))


class ExperimentResult(Base):
    __tablename__ = 'experiment_result'
    __table_args__ = (
        sa.UniqueConstraint('experiment_id', 'predictor_type', 'predictor_name', name='UQ_experiment_result'),
        _nonempty_check('predictor_name', 'CK_experiment_result_name'),
        sa.CheckConstraint("predictor_type IN ('ANNOTATOR', 'METHOD')", name='CK_experiment_result_type'),
        sa.CheckConstraint('mae >= 0', name='CK_experiment_result_mae'),
        sa.CheckConstraint('rmse >= 0', name='CK_experiment_result_rmse'),
        {'schema': 'dahlia'},
    )
    experiment_result_id: Mapped[int] = _identity()
    experiment_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('dahlia.experiment.experiment_id'))
    predictor_type: Mapped[str] = mapped_column(sa.Unicode(16))
    predictor_name: Mapped[str] = mapped_column(sa.Unicode(128))
    mae: Mapped[float] = mapped_column(sa.Float(53))
    rmse: Mapped[float] = mapped_column(sa.Float(53))

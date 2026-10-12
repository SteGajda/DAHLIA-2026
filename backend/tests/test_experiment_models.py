"""Scientific model constraints and round trips in isolated test databases."""

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mssql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.models.user import AppUser
from app.models.experiment import (
    Dataset, PredefinedSet, PredefinedSetPoint, Experiment,
    ExperimentPoint, PointPrediction, ExperimentResult,
)


def seed_dataset(session, engine):
    with engine.connect() as conn:
        conn.exec_driver_sql('PRAGMA foreign_keys=ON')
    user = AppUser(email='models@example.com', display_name='Model test', password_hash='unused')
    session.add(user)
    session.flush()
    csv = b'Id,value\n1,4.2\n2,5.1\n'
    dataset = Dataset(
        name='iris', csv_file_name='iris.csv', csv_file=csv,
        csv_sha256=hashlib.sha256(csv).digest(), row_count=2,
        imputed_column='value', target_column=None,
        reference_columns_json='[]', precision_value=Decimal('0.1'),
        created_by=user.user_id,
    )
    session.add(dataset)
    session.flush()
    return user, dataset


def make_experiment(user, dataset, **changes):
    values = dict(
        experiment_uid=uuid4(), annotator_id=user.user_id,
        dataset_id=dataset.dataset_id, source_type='SEEDED', seed=42,
        na_fraction=Decimal('0.1'), projection='pca',
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None), app_version='1.1.0',
    )
    values.update(changes)
    return Experiment(**values)


def test_complete_experiment_graph_roundtrip(sqlite_session, sqlite_engine):
    s = sqlite_session
    user, dataset = seed_dataset(s, sqlite_engine)
    experiment = make_experiment(user, dataset)
    s.add(experiment)
    s.flush()
    point = ExperimentPoint(experiment_id=experiment.experiment_id, row_index=0,
                            annotation_order=1, true_value=4.2)
    other = ExperimentPoint(experiment_id=experiment.experiment_id, row_index=1,
                            annotation_order=None, true_value=5.1)
    s.add_all([point, other])
    s.flush()
    s.add_all([
        PointPrediction(experiment_point_id=point.experiment_point_id,
                        predictor_type='ANNOTATOR', predictor_name='Annotator', predicted_value=4.0),
        PointPrediction(experiment_point_id=other.experiment_point_id,
                        predictor_type='METHOD', predictor_name='Mean', predicted_value=4.6),
        ExperimentResult(experiment_id=experiment.experiment_id,
                         predictor_type='ANNOTATOR', predictor_name='Annotator', mae=0.2, rmse=0.2),
    ])
    s.commit()
    s.expire_all()
    loaded = s.scalar(select(Experiment))
    assert loaded.experiment_uid == experiment.experiment_uid
    assert loaded.na_fraction == Decimal('0.100000')
    assert s.scalar(select(Dataset)).csv_file == dataset.csv_file
    points = s.scalars(select(ExperimentPoint).order_by(ExperimentPoint.row_index)).all()
    assert [p.annotation_order for p in points] == [1, None]
    assert len(s.scalars(select(PointPrediction)).all()) == 2
    assert s.scalar(select(ExperimentResult)).mae == pytest.approx(0.2)


def test_duplicate_experiment_uuid_is_rejected(sqlite_session, sqlite_engine):
    user, dataset = seed_dataset(sqlite_session, sqlite_engine)
    uid = uuid4()
    sqlite_session.add(make_experiment(user, dataset, experiment_uid=uid))
    sqlite_session.flush()
    sqlite_session.add(make_experiment(user, dataset, experiment_uid=uid))
    with pytest.raises(IntegrityError):
        sqlite_session.flush()
    sqlite_session.rollback()


@pytest.mark.parametrize('changes', [
    {'source_type': 'SEEDED', 'seed': None},
    {'source_type': 'PREDEFINED', 'seed': None, 'predefined_set_id': None},
    {'projection': 'invalid'},
    {'na_fraction': Decimal('1.0')},
])
def test_invalid_experiment_configuration_is_rejected(sqlite_session, sqlite_engine, changes):
    user, dataset = seed_dataset(sqlite_session, sqlite_engine)
    sqlite_session.add(make_experiment(user, dataset, **changes))
    with pytest.raises(IntegrityError):
        sqlite_session.flush()
    sqlite_session.rollback()


def test_predefined_set_and_points_roundtrip(sqlite_session, sqlite_engine):
    s = sqlite_session
    user, dataset = seed_dataset(s, sqlite_engine)
    predefined = PredefinedSet(name='fixed', dataset_id=dataset.dataset_id,
                               na_fraction=Decimal('0.1'), created_by=user.user_id)
    s.add(predefined)
    s.flush()
    s.add(PredefinedSetPoint(predefined_set_id=predefined.predefined_set_id,
                            row_index=0, annotation_order=1))
    s.add(make_experiment(user, dataset, source_type='PREDEFINED', seed=None,
                          predefined_set_id=predefined.predefined_set_id))
    s.commit()
    assert s.scalar(select(Experiment)).source_type == 'PREDEFINED'
    assert s.scalar(select(PredefinedSetPoint)).row_index == 0


def test_predefined_set_fraction_must_match_experiment(sqlite_session, sqlite_engine):
    s = sqlite_session
    user, dataset = seed_dataset(s, sqlite_engine)
    predefined = PredefinedSet(name='fixed', dataset_id=dataset.dataset_id,
                               na_fraction=Decimal('0.1'), created_by=user.user_id)
    s.add(predefined)
    s.flush()
    s.add(make_experiment(user, dataset, source_type='PREDEFINED', seed=None,
                          predefined_set_id=predefined.predefined_set_id,
                          na_fraction=Decimal('0.2')))
    with pytest.raises(IntegrityError):
        s.flush()
    s.rollback()


def test_sql_server_storage_types_compile_correctly():
    dataset_ddl = str(CreateTable(Dataset.__table__).compile(dialect=mssql.dialect()))
    experiment_ddl = str(CreateTable(Experiment.__table__).compile(dialect=mssql.dialect()))
    assert 'VARBINARY(max)' in dataset_ddl
    assert 'BINARY(32)' in dataset_ddl
    assert 'NVARCHAR(max)' in dataset_ddl
    assert 'ISJSON(reference_columns_json)' in dataset_ddl
    assert 'UNIQUEIDENTIFIER' in experiment_ddl
    assert 'DATETIME2(3)' in experiment_ddl

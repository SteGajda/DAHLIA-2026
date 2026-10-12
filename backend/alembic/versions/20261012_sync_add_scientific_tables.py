"""Adopt/create scientific tables and add payload identity for synchronization.

Existing tables created by 003_create_tables.sql are retained. Missing tables
are created for new SQL Server/Azure deployments. This adoption is forward-only
because a downgrade must not drop independently created scientific data.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mssql
from alembic import op

from app.db.base import Base

revision = '20261012_sync'
down_revision = '2773cde4ae88'
branch_labels = None
depends_on = None

SCIENTIFIC_TABLES = {
    'dataset', 'predefined_set', 'predefined_set_point', 'experiment',
    'experiment_point', 'point_prediction', 'experiment_result',
}
PAYLOAD_COLUMNS = {'payload_json', 'payload_sha256'}


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'mssql':
        raise RuntimeError('DAHLIA Alembic migrations require SQL Server/Azure SQL.')
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names(schema='dahlia'))
    tables = [table for table in Base.metadata.sorted_tables if table.name in SCIENTIFIC_TABLES]
    # Validate before performing any DDL. Preserve all existing tables and rows.
    for table in tables:
        if table.name not in existing:
            continue
        columns = {column['name'] for column in inspector.get_columns(table.name, schema='dahlia')}
        expected = set(table.columns.keys())
        if table.name == 'experiment':
            expected -= PAYLOAD_COLUMNS
        missing = expected - columns
        if missing:
            raise RuntimeError(f'Existing dahlia.{table.name} is missing columns: {sorted(missing)}')
        actual_pk = inspector.get_pk_constraint(table.name, schema='dahlia')['constrained_columns']
        if actual_pk != [column.name for column in table.primary_key.columns]:
            raise RuntimeError(f'Unexpected primary key on dahlia.{table.name}.')
    for table in tables:
        if table.name not in existing:
            table.create(bind=bind)
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('experiment', schema='dahlia')}
    if 'payload_json' not in columns:
        op.add_column('experiment', sa.Column('payload_json', mssql.NVARCHAR(), nullable=True), schema='dahlia')
    if 'payload_sha256' not in columns:
        op.add_column('experiment', sa.Column('payload_sha256', mssql.BINARY(32), nullable=True), schema='dahlia')
    checks = set(bind.execute(
        sa.text('SELECT name FROM sys.check_constraints '
                'WHERE parent_object_id = OBJECT_ID(:table_name)'),
        {'table_name': 'dahlia.experiment'},
    ).scalars())
    if 'CK_experiment_payload_json' not in checks:
        op.create_check_constraint('CK_experiment_payload_json', 'experiment',
                                   'payload_json IS NULL OR ISJSON(payload_json) = 1', schema='dahlia')


def downgrade():
    raise RuntimeError('Scientific-table adoption is forward-only; no existing data was dropped.')

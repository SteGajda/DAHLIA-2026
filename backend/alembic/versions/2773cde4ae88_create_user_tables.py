"""Create user tables: app_user, refresh_token, role_request.

Revision ID: 2773cde4ae88
Revises:
Create Date: 2026-09-21 05:11:52.126805
"""

from __future__ import annotations

from typing import Sequence, Union

import alembic.op as op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2773cde4ae88'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration (forward direction).

    1. Creates the ``dahlia`` schema if it does not already exist.
    2. Creates ``app_user``, ``refresh_token``, and ``role_request`` tables.
    """
    # Schema creation
    op.execute(
        sa.text(
            "IF NOT EXISTS "
            "(SELECT 1 FROM sys.schemas WHERE name = 'dahlia') "
            "EXEC('CREATE SCHEMA dahlia')"
        )
    )

    # Table: app_user
    op.create_table(
        'app_user',
        sa.Column('user_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role_code', sa.String(length=20), nullable=False),
        sa.Column('is_pw_affiliated', sa.Boolean(), nullable=False),
        sa.Column('student_id_number', sa.String(length=32), nullable=True),
        sa.Column('consent_given', sa.Boolean(), nullable=False),
        sa.Column('is_email_verified', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
        schema='dahlia',
    )
    with op.batch_alter_table('app_user', schema='dahlia') as batch_op:
        batch_op.create_index(
            batch_op.f('ix_dahlia_app_user_email'), ['email'], unique=True
        )

    # Table: refresh_token
    op.create_table(
        'refresh_token',
        sa.Column('token_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['dahlia.app_user.user_id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('token_id'),
        schema='dahlia',
    )
    with op.batch_alter_table('refresh_token', schema='dahlia') as batch_op:
        batch_op.create_index(
            batch_op.f('ix_dahlia_refresh_token_token_hash'),
            ['token_hash'],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f('ix_dahlia_refresh_token_user_id'),
            ['user_id'],
            unique=False,
        )

    # Table: role_request
    op.create_table(
        'role_request',
        sa.Column('request_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('requested_role', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reviewed_by', sa.BigInteger(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['reviewed_by'], ['dahlia.app_user.user_id'], ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['dahlia.app_user.user_id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('request_id'),
        schema='dahlia',
    )
    with op.batch_alter_table('role_request', schema='dahlia') as batch_op:
        batch_op.create_index(
            batch_op.f('ix_dahlia_role_request_user_id'), ['user_id'], unique=False
        )


def downgrade() -> None:
    """Roll back the migration (reverse direction).

    Drops all three tables in reverse dependency order, then removes the
    ``dahlia`` schema.
    """
    with op.batch_alter_table('role_request', schema='dahlia') as batch_op:
        batch_op.drop_index(batch_op.f('ix_dahlia_role_request_user_id'))
    op.drop_table('role_request', schema='dahlia')

    with op.batch_alter_table('refresh_token', schema='dahlia') as batch_op:
        batch_op.drop_index(batch_op.f('ix_dahlia_refresh_token_user_id'))
        batch_op.drop_index(batch_op.f('ix_dahlia_refresh_token_token_hash'))
    op.drop_table('refresh_token', schema='dahlia')

    with op.batch_alter_table('app_user', schema='dahlia') as batch_op:
        batch_op.drop_index(batch_op.f('ix_dahlia_app_user_email'))
    op.drop_table('app_user', schema='dahlia')

    op.execute(sa.text("DROP SCHEMA IF EXISTS dahlia"))

"""Add a persistent per-account verification mail cooldown."""

from alembic import op
import sqlalchemy as sa

revision = "20261020_email"
down_revision = "20261012_sync"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "mssql":
        raise RuntimeError("DAHLIA Alembic migrations require SQL Server/Azure SQL.")
    op.add_column("app_user", sa.Column(
        "email_verification_sent_at", sa.DateTime(timezone=True), nullable=True,
    ), schema="dahlia")


def downgrade():
    op.drop_column("app_user", "email_verification_sent_at", schema="dahlia")

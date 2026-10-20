"""Individual SQL read access for eligible verified application accounts."""

from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "20261020_sql_access"
down_revision = "20261020_email"
branch_labels = None
depends_on = None

TABLES = ("dataset", "predefined_set", "predefined_set_point", "experiment",
          "experiment_point", "point_prediction", "experiment_result")


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "mssql":
        raise RuntimeError("Use SQL Server/Azure SQL for Alembic migrations.")
    op.add_column("app_user", sa.Column("sql_username", sa.String(128), nullable=True), schema="dahlia")
    op.add_column("app_user", sa.Column("sql_password_issued_at", sa.DateTime(timezone=True), nullable=True), schema="dahlia")
    op.add_column("app_user", sa.Column("sql_client_ipv4", sa.String(15), nullable=True), schema="dahlia")
    # SQL Server unique constraints allow only one NULL, so use a filtered index.
    op.create_index("UX_app_user_sql_username", "app_user", ["sql_username"], unique=True,
                    schema="dahlia", mssql_where=sa.text("sql_username IS NOT NULL"))
    bind.exec_driver_sql("CREATE ROLE [dahlia_results_reader] AUTHORIZATION [dbo]")
    for table in TABLES:
        bind.exec_driver_sql(f"GRANT SELECT ON OBJECT::[dahlia].[{table}] TO [dahlia_results_reader]")
    script = (Path(__file__).resolve().parents[2] / "sql" / "readonly_access.sql").read_text(encoding="utf-8")
    # GO is a client separator, not a T-SQL statement.
    for batch in script.split("\nGO\n"):
        if batch.strip():
            bind.exec_driver_sql(batch)
    bind.exec_driver_sql("""
        IF USER_ID(N'dahlia_api') IS NOT NULL
            GRANT EXECUTE ON OBJECT::dahlia.manage_readonly_access TO [dahlia_api];
    """)


def downgrade():
    raise RuntimeError("Revoke managed SQL accounts explicitly before removing this feature.")

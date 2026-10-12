"""Compile the actual refresh endpoint query for SQL Server, not only SQLite."""

from sqlalchemy import event
from sqlalchemy.dialects import mssql
from sqlalchemy.sql import Select


def test_refresh_uses_valid_sql_server_bit_comparison(client, sqlite_engine):
    client.post('/api/v1/auth/register', json={
        'email': 'refresh-sql@example.com', 'password': 'testpassword123',
        'display_name': 'Refresh SQL test', 'is_pw_affiliated': False,
        'consent_given': True,
    })
    login = client.post('/api/v1/auth/login', json={
        'email': 'refresh-sql@example.com', 'password': 'testpassword123',
    })
    assert login.status_code == 200
    statements = []

    def capture(conn, clauseelement, multiparams, params, execution_options):
        if isinstance(clauseelement, Select):
            sql = str(clauseelement.compile(dialect=mssql.dialect()))
            if 'refresh_token.expires_at >' in sql:
                statements.append(sql)

    event.listen(sqlite_engine, 'before_execute', capture)
    try:
        response = client.post('/api/v1/auth/refresh', json={
            'refresh_token': login.json()['refresh_token'],
        })
    finally:
        event.remove(sqlite_engine, 'before_execute', capture)
    assert response.status_code == 200
    assert len(statements) == 1
    assert 'refresh_token.revoked = 0' in statements[0]
    assert 'refresh_token.revoked IS 0' not in statements[0]

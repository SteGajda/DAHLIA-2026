[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$BackendPath = Split-Path -Parent $PSScriptRoot
$ProjectPath = Split-Path -Parent $BackendPath
$PythonPath = Join-Path $ProjectPath ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonPath)) { throw "Missing project .venv." }
$credential = Get-Credential -UserName "dahlia_admin" -Message "Existing Azure SQL administrator password"
if (-not $credential) { throw "Credentials are required." }
$previous = $env:DAHLIA_SQL_PASSWORD
$env:DAHLIA_SQL_PASSWORD = $credential.GetNetworkCredential().Password
Push-Location $BackendPath
try {
@'
import os
import secrets
import subprocess
import sys
import time
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

url = URL.create(
    "mssql+pyodbc", username="dahlia_admin", password=os.environ["DAHLIA_SQL_PASSWORD"],
    host="dahlia-2026.database.windows.net", port=1433, database="DAHLIA",
    query={"driver": "ODBC Driver 18 for SQL Server", "Encrypt": "yes", "TrustServerCertificate": "no"},
)
engine = create_engine(url, hide_parameters=True, connect_args={"timeout": 30})
try:
    for attempt in range(4):
        try:
            with engine.connect() as conn:
                row = conn.execute(text("SELECT DB_NAME(), CONVERT(int, SERVERPROPERTY('EngineEdition'))")).one()
                if row[0] != "DAHLIA" or int(row[1]) != 5:
                    raise SystemExit("Unexpected migration target.")
            break
        except DBAPIError as error:
            if "40613" not in str(error.orig) or attempt == 3:
                raise SystemExit("Azure SQL connection failed: " + str(error.orig).replace(os.environ["DAHLIA_SQL_PASSWORD"], "[hidden]")) from None
            print("Azure database is waking up; retrying in 20 seconds...", flush=True)
            time.sleep(20)
    print("Migration target: Azure SQL / DAHLIA", flush=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = url.render_as_string(hide_password=False)
    # This process only runs migrations; the deployed JWT secret is unchanged.
    env["SECRET_KEY"] = secrets.token_hex(32)
    env["APP_ENV"] = "development"
    env["EMAIL_DELIVERY_MODE"] = "disabled"
    env["SQL_ACCESS_ENABLED"] = "false"
    for arguments in (["upgrade", "20261020_sql_access"], ["current"]):
        result = subprocess.run([sys.executable, "-m", "alembic", *arguments], env=env)
        if result.returncode:
            raise SystemExit(result.returncode)
    print("SQL access migration: OK", flush=True)
finally:
    engine.dispose()
'@ | & $PythonPath -
    if ($LASTEXITCODE -ne 0) { throw "SQL access migration failed. Do not deploy the new backend yet." }
}
finally {
    Pop-Location
    $env:DAHLIA_SQL_PASSWORD = $previous
    $credential = $null
    $previous = $null
}

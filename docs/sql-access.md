# Individual read-only SQL access

## Permissions

| Application role | SQL account |
| --- | --- |
| USER | No direct SQL account |
| USER_PLUS | Personal read-only account |
| RESEARCHER | Personal read-only account |
| DEVELOPER | Personal read-only account; application admin privileges do not grant SQL administration |

An account must also be active and have a verified email. Eligible users activate access in Profile > Database access (SSMS). Activation/reset returns a generated SQL password once, with a 60-second cooldown. A reset replaces the previous password. Do not share the application password or the SQL administrator password.

The `dahlia_results_reader` database role receives SELECT on exactly these existing scientific tables: dataset, predefined_set, predefined_set_point, experiment, experiment_point, point_prediction, experiment_result. It grants no data writes, schema changes, user administration or access to app_user, refresh_token and role_request. Researchers can read all shared experiment rows, including numerical user IDs. This is direct database access, not a per-user results view.

The runtime dahlia_api account receives EXECUTE on one owner-executed provisioning procedure, not CONTROL or ALTER ANY USER. The procedure validates eligibility again under a row lock. Existing SQL principals are never adopted without the matching application mapping. The application stores only the SQL username, issue timestamp and last authorized IPv4; it does not store the generated SQL password.

The database trigger revokes managed access on role downgrade to USER, account deactivation, loss of email verification or deletion. It denies new connections, removes reader membership, and denies SELECT on scientific tables to cover future queries in existing sessions. Already running queries and data previously downloaded are unaffected. Upgrading an account again requires regenerating credentials. Deleting the application account does not drop its SQL principal automatically.

## IP firewall

Activation also creates/updates a single-IP database-level firewall rule for the public IPv4 supplied by the user. Find that address on the same network where SSMS runs, for example in PowerShell:

```powershell
Invoke-RestMethod "https://api4.ipify.org"
```

The firewall allows a network address; it is not bound to one SQL login. SQL authentication and SQL permissions still control access. Each account maintains one rule. Reset after changing networks to replace the rule. Deactivation leaves the IP rule in place but revokes that SQL account's permissions. An administrator can remove obsolete rules using sys.sp_delete_database_firewall_rule. No 0.0.0.0 Allow Azure rule is created.

Database-level firewall rules require CONTROL on the database. Only the owner-executed procedure uses that privilege; the runtime account and reader users do not receive it. See https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-set-database-firewall-rule-azure-sql-database.

## Deployment order (PowerShell, project root)

First pass the frontend/backend tests with SQL_ACCESS_ENABLED=false, SQLite and EMAIL_DELIVERY_MODE=disabled. Then migrate Azure using the existing dahlia_admin password:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\backend\scripts\migrate_sql_access.ps1
```

Expected revision: `20261020_sql_access (head)`. The migration adds three nullable app_user columns and a filtered index, the reader role, two procedures and a trigger. It does not replace scientific data. The existing 0.3.0 backend can keep running during the migration. This migration is forward-only; do not use downgrade to remove managed accounts.

Only after successful migration, build and publish the updated backend image:

```powershell
& {
    docker build --platform linux/amd64 -t gajdas/dahlia-backend:0.4.0 .\backend
    if ($LASTEXITCODE -ne 0) { throw "Docker build failed." }
    docker push gajdas/dahlia-backend:0.4.0
    if ($LASTEXITCODE -ne 0) { throw "Docker push failed." }
    az containerapp update --name dahlia-api --resource-group rg-dahlia `
        --image docker.io/gajdas/dahlia-backend:0.4.0 `
        --set-env-vars SQL_ACCESS_ENABLED=true SQL_ACCESS_HOST=dahlia-2026.database.windows.net SQL_ACCESS_DATABASE=DAHLIA `
        --output none
    if ($LASTEXITCODE -ne 0) { throw "Backend deployment failed." }
}
az containerapp show --name dahlia-api --resource-group rg-dahlia `
    --query "{State:properties.provisioningState,Latest:properties.latestRevisionName,Ready:properties.latestReadyRevisionName,Image:properties.template.containers[0].image}" --output table
```

This updates the image and three nonsecret settings. Existing database URL, JWT secret, SMTP settings and Docker Hub credentials remain configured in Container Apps. Provisioning is disabled by default in local development. No GitHub operations are performed by these commands.

Restart the frontend from source, or rebuild the EXE with the existing build script after deployment. Every rebuild includes current source. Existing EXEs do not update themselves.

## SSMS connection

In the new Profile panel, enter your public IPv4 and activate access. Save the password before closing the dialog. In SSMS use:

- Server: dahlia-2026.database.windows.net
- Authentication: SQL Server Authentication
- Login: the personal dahlia_ro_<id> shown by the application
- Password: the generated SQL password
- Database / Connect to database: DAHLIA (required for this contained user; do not connect to master)
- Encryption enabled, Trust server certificate disabled

## Live acceptance test (required before distributing the new EXE)

Unit tests use SQLite/mocks and cannot verify Azure stored procedures, firewall rules or revocation. Test these against Azure after deployment:

1. A verified DEVELOPER activates access and connects through SSMS. Run SELECT TOP (10) * FROM dahlia.experiment; and SELECT USER_NAME(), DB_NAME();.
2. With the read-only SQL account, run UPDATE dahlia.dataset SET name=name WHERE 1=0;. It must fail with a permission error even though no rows match. SELECT * FROM dahlia.app_user; must also fail.
3. Repeat for a separate verified USER_PLUS or RESEARCHER app account; its SQL username must differ. A USER must receive 403 from the credentials endpoint.
4. As administrator, downgrade the separate test application account to USER or set is_active=0. Its next SSMS query must be denied, and reconnect must fail. Do not deactivate your only administrator for this test.
5. Restore eligibility, generate new credentials (after the cooldown), and verify SELECT again. Check the old password no longer opens a new connection after a reset.

If provisioning returns 503, inspect the migration/role and the Container Apps system logs. Password-bearing SQL exceptions are intentionally not returned or logged by the credential service. Do not paste passwords or tokens into issue reports. Disabling SQL_ACCESS_ENABLED blocks new activation/reset requests; it does not revoke already issued SQL credentials.

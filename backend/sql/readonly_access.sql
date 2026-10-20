CREATE PROCEDURE [dahlia].[revoke_readonly_access]
    @user_id bigint
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @name sysname = N'dahlia_ro_' + CONVERT(nvarchar(20), @user_id);
    -- Only the owner/trigger can execute this procedure; no application EXECUTE grant.
    -- Derive the name so deletion of the application row can revoke it as well.
    IF USER_ID(@name) IS NULL RETURN;
    DECLARE @sql nvarchar(max) = N'DENY CONNECT TO ' + QUOTENAME(@name) + N';';
    IF EXISTS (
        SELECT 1 FROM sys.database_role_members
        WHERE role_principal_id=DATABASE_PRINCIPAL_ID(N'dahlia_results_reader')
          AND member_principal_id=DATABASE_PRINCIPAL_ID(@name)
    )
        SET @sql += N'ALTER ROLE [dahlia_results_reader] DROP MEMBER ' + QUOTENAME(@name) + N';';
    -- Object DENYs also prevent research queries from sessions opened earlier.
    SET @sql += N'DENY SELECT ON OBJECT::dahlia.dataset TO ' + QUOTENAME(@name) + N';'
        + N'DENY SELECT ON OBJECT::dahlia.predefined_set TO ' + QUOTENAME(@name) + N';'
        + N'DENY SELECT ON OBJECT::dahlia.predefined_set_point TO ' + QUOTENAME(@name) + N';'
        + N'DENY SELECT ON OBJECT::dahlia.experiment TO ' + QUOTENAME(@name) + N';'
        + N'DENY SELECT ON OBJECT::dahlia.experiment_point TO ' + QUOTENAME(@name) + N';'
        + N'DENY SELECT ON OBJECT::dahlia.point_prediction TO ' + QUOTENAME(@name) + N';'
        + N'DENY SELECT ON OBJECT::dahlia.experiment_result TO ' + QUOTENAME(@name) + N';';
    EXEC sys.sp_executesql @sql;
END;
GO
CREATE PROCEDURE [dahlia].[manage_readonly_access]
    @user_id bigint,
    @password nvarchar(128),
    @client_ipv4 varchar(15)
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF CONVERT(int, SERVERPROPERTY('EngineEdition')) <> 5
        THROW 51004, 'This feature is configured for Azure SQL Database only.', 1;

    -- Reject malformed input and the special 0.0.0.0 Allow Azure firewall rule.
    IF @client_ipv4 IS NULL OR @client_ipv4 LIKE '%[^0-9.]%'
       OR LEN(@client_ipv4)-LEN(REPLACE(@client_ipv4,'.','')) <> 3
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,4)) IS NULL
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,3)) IS NULL
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,2)) IS NULL
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,1)) IS NULL
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,4)) NOT BETWEEN 1 AND 223
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,4)) IN (10,127)
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,3)) NOT BETWEEN 0 AND 255
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,2)) NOT BETWEEN 0 AND 255
       OR TRY_CONVERT(int,PARSENAME(@client_ipv4,1)) NOT BETWEEN 0 AND 255
        THROW 51003, 'A public IPv4 address is required.', 1;
    IF @password IS NULL OR LEN(@password) NOT BETWEEN 16 AND 128
        THROW 51003, 'Invalid SQL password.', 1;

    DECLARE @role varchar(20), @active bit, @verified bit, @existing sysname,
            @issued datetimeoffset, @found bigint;
    SELECT @found=user_id, @role=role_code, @active=is_active,
           @verified=is_email_verified, @existing=sql_username,
           @issued=sql_password_issued_at
    FROM dahlia.app_user WITH (UPDLOCK, HOLDLOCK) WHERE user_id=@user_id;
    IF @found IS NULL OR @active <> 1 OR @verified <> 1
       OR @role NOT IN ('USER_PLUS','RESEARCHER','DEVELOPER')
        THROW 51001, 'The application account is not eligible for SQL access.', 1;
    IF @issued > DATEADD(second, -60, SYSDATETIMEOFFSET())
        THROW 51002, 'Wait before resetting SQL credentials.', 1;

    DECLARE @name sysname = N'dahlia_ro_' + CONVERT(nvarchar(20), @user_id);
    -- Never adopt an unrelated principal with a coincidentally matching name.
    IF USER_ID(@name) IS NOT NULL AND (@existing IS NULL OR @existing <> @name)
        THROW 51005, 'SQL principal name conflict.', 1;

    DECLARE @sql nvarchar(max);
    IF USER_ID(@name) IS NULL
        SET @sql = N'CREATE USER ' + QUOTENAME(@name) + N' WITH PASSWORD = '
                   + QUOTENAME(@password,CHAR(39)) + N', DEFAULT_SCHEMA=[dahlia];';
    ELSE
        SET @sql = N'ALTER USER ' + QUOTENAME(@name) + N' WITH PASSWORD = '
                   + QUOTENAME(@password,CHAR(39)) + N';';
    EXEC sys.sp_executesql @sql;

    SET @sql = N'REVOKE CONNECT FROM ' + QUOTENAME(@name) + N';GRANT CONNECT TO ' + QUOTENAME(@name) + N';'
        + N'REVOKE SELECT ON OBJECT::dahlia.dataset FROM ' + QUOTENAME(@name) + N';'
        + N'REVOKE SELECT ON OBJECT::dahlia.predefined_set FROM ' + QUOTENAME(@name) + N';'
        + N'REVOKE SELECT ON OBJECT::dahlia.predefined_set_point FROM ' + QUOTENAME(@name) + N';'
        + N'REVOKE SELECT ON OBJECT::dahlia.experiment FROM ' + QUOTENAME(@name) + N';'
        + N'REVOKE SELECT ON OBJECT::dahlia.experiment_point FROM ' + QUOTENAME(@name) + N';'
        + N'REVOKE SELECT ON OBJECT::dahlia.point_prediction FROM ' + QUOTENAME(@name) + N';'
        + N'REVOKE SELECT ON OBJECT::dahlia.experiment_result FROM ' + QUOTENAME(@name) + N';';
    EXEC sys.sp_executesql @sql;
    IF NOT EXISTS (
        SELECT 1 FROM sys.database_role_members
        WHERE role_principal_id=DATABASE_PRINCIPAL_ID(N'dahlia_results_reader')
          AND member_principal_id=DATABASE_PRINCIPAL_ID(@name)
    )
    BEGIN
        SET @sql = N'ALTER ROLE [dahlia_results_reader] ADD MEMBER ' + QUOTENAME(@name) + N';';
        EXEC sys.sp_executesql @sql;
    END;

    DECLARE @firewall_name nvarchar(128) = N'dahlia-ro-' + CONVERT(nvarchar(20), @user_id);
    EXEC sys.sp_set_database_firewall_rule @name=@firewall_name,
         @start_ip_address=@client_ipv4, @end_ip_address=@client_ipv4;

    UPDATE dahlia.app_user SET sql_username=@name,
        sql_password_issued_at=SYSDATETIMEOFFSET(), sql_client_ipv4=@client_ipv4
    WHERE user_id=@user_id;
END;
GO
CREATE TRIGGER [dahlia].[TR_app_user_readonly_access]
ON [dahlia].[app_user]
WITH EXECUTE AS OWNER
AFTER UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM inserted) AND NOT
       (UPDATE(role_code) OR UPDATE(is_active) OR UPDATE(is_email_verified)) RETURN;
    DECLARE @id bigint;
    DECLARE users_to_revoke CURSOR LOCAL FAST_FORWARD FOR
        SELECT old.user_id FROM deleted AS old
        LEFT JOIN inserted AS current_user_row ON old.user_id=current_user_row.user_id
        WHERE old.sql_username=N'dahlia_ro_' + CONVERT(nvarchar(20), old.user_id) AND
          (current_user_row.user_id IS NULL
           OR current_user_row.role_code NOT IN ('USER_PLUS','RESEARCHER','DEVELOPER')
           OR current_user_row.is_active=0 OR current_user_row.is_email_verified=0);
    OPEN users_to_revoke;
    FETCH NEXT FROM users_to_revoke INTO @id;
    WHILE @@FETCH_STATUS=0
    BEGIN
        EXEC dahlia.revoke_readonly_access @user_id=@id;
        FETCH NEXT FROM users_to_revoke INTO @id;
    END;
    CLOSE users_to_revoke;
    DEALLOCATE users_to_revoke;
END;

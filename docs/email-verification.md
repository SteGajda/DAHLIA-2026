# Email verification

Backend SMTP sender: `dahlia.imputation@gmail.com`. SMTP secrets never belong in
the frontend, the Windows EXE, Git, or a deployment image.

## Flow

1. Registration creates an unverified account and submits a message to SMTP.
2. An existing user can log in and use Profile → Send verification email.
3. The recipient opens the link and explicitly clicks Confirm email.
4. Profile → Check verification status fetches `/api/v1/auth/me` again.
5. The sync API checks verification in the database on every upload. It returns
   403 for unverified accounts, even with a valid access token.

The mail link points to the backend, not to a NiceGUI process on a user's PC.
The JWT is in the URL fragment, not a query parameter or access log. The page
removes the fragment from the address bar and uses POST after a click. It has
no external resources, a nonce-based script policy, and no-store/no-referrer
headers. Opening a link alone does not change verification state.

Links expire after 24 hours. A newly issued token is bound to the email address.
Older signed verification tokens remain compatible until their original expiry.
Repeated confirmation is idempotent. The authenticated resend endpoint accepts
no recipient override. A conditional database UPDATE reserves a per-account
60-second cooldown, including when SMTP fails. This survives process restarts
and does not depend on the number of containers. A resend does not revoke older
unexpired links for the same unchanged address.

## Configuration

Enable Google 2-Step Verification and generate an app password for this account.
Use an app password, not the normal Google account password.

Configure these only on the backend:

```dotenv
EMAIL_DELIVERY_MODE=smtp
PUBLIC_API_URL=https://dahlia-api.lemonwave-82fa477c.germanywestcentral.azurecontainerapps.io
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=dahlia.imputation@gmail.com
SMTP_FROM_EMAIL=dahlia.imputation@gmail.com
SMTP_PASSWORD=<Google app password>
SMTP_TIMEOUT_SECONDS=20
EMAIL_RESEND_COOLDOWN_SECONDS=60
```

For local testing, PUBLIC_API_URL must be `http://127.0.0.1:8000` and the local
backend must remain running while the email link is opened. Local and Azure
accounts, databases and signing keys are separate; local links cannot verify
cloud accounts. Production requires an HTTPS origin.

`EMAIL_DELIVERY_MODE=disabled` is the safe default before configuring SMTP.
Registration still creates an account and explains that mail was not sent.
SMTP failure never verifies a user or rolls back an already created account.
The user can sign in and retry after the cooldown. `email_sent` means SMTP
accepted the submission, not a guarantee that the message reached the inbox.

TLS STARTTLS is mandatory, with normal certificate/hostname verification. The
SMTP password uses Pydantic SecretStr and provider errors are not returned to
the client. Verification tokens are no longer logged. The separate legacy
password-reset flow is not changed by this patch and still requires its own
delivery implementation.

## Migration and deployment order

The new nullable app_user.email_verification_sent_at column requires Alembic
upgrade to `20261020_email` on SQL Server/Azure SQL. Existing accounts, data and
verification flags are preserved. Run migrations with an administrator account;
the `dahlia_api` runtime account does not have DDL permissions.

1. Apply code and run tests with SQLite and email delivery disabled.
2. Apply the migration to the intended SQL database using Alembic upgrade head.
   Do not use stamp. Do not print database URLs or secrets.
3. Configure backend SMTP credentials locally or in Container Apps secrets.
4. Build and publish a new backend image, e.g. gajdas/dahlia-backend:0.3.0, and
   update Container Apps. Add SMTP_PASSWORD as a secretRef, with the other email
   settings as container environment variables. Keep the existing database-url,
   jwt-secret and registry secret intact. Never rotate SECRET_KEY merely to
   deploy this patch.
5. Restart the frontend with DAHLIA_API_URL set to the same target.
6. Test Send verification email → inbox → Confirm email → Check verification
   status → manual upload. Check spam. Do not paste tokens or app passwords
   into issue reports.

Changing files on Windows does not update the existing Azure image 0.2.0.
Migration must precede activation of the new image because the ORM selects the
new column. Settings changes require a backend restart/new revision.

SQLite create_all is for fresh development/test databases only: it does not
add a column to an existing SQLite file. Do not delete a database containing
data to work around a migration error. The frontend SQLite buffer is unrelated
and needs no changes.

## Tests and limits

Tests cover authenticated resend, cooldown, actual verification route, invalid
and expired tokens, email binding, no verification by GET, TLS enforcement,
frontend profile refresh and the backend upload gate. SMTP is mocked in tests;
real Gmail delivery and the Azure SQL migration must be verified on deployment.
The existing cold-start behavior and dynamic SQL firewall address are separate
deployment concerns, unchanged here. Account-level cooldown does not replace
application-wide registration rate limiting before a wider public rollout.

## Sources

- https://support.google.com/mail/answer/185833
- https://support.google.com/mail/answer/7104828
- https://docs.python.org/3.12/library/smtplib.html
- https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html

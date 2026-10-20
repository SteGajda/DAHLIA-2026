"""Static confirmation page; opening a link alone never verifies an account."""

import secrets

from fastapi.responses import HTMLResponse


def verification_page() -> HTMLResponse:
    nonce = secrets.token_urlsafe(24)
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>DAHLIA email verification</title>
<style>body{font:18px system-ui,sans-serif;background:#f7f7f5;color:#222;
margin:12vh auto;padding:24px;max-width:600px}button{font:inherit;padding:12px 20px;
cursor:pointer}#status{line-height:1.6}</style></head>
<body><h1>DAHLIA</h1><h2>Confirm your email address</h2>
<p id="status">Click Confirm email to finish verification.</p>
<button id="confirm" type="button">Confirm email</button>
<script nonce="__NONCE__">
const params = new URLSearchParams(window.location.hash.slice(1));
let token = params.get('token');
history.replaceState(null, '', window.location.pathname);
const status = document.getElementById('status');
const button = document.getElementById('confirm');
if (!token) {
  status.textContent = 'Open the full link from your verification email.';
  button.disabled = true;
}
button.addEventListener('click', async () => {
  button.disabled = true;
  status.textContent = 'Confirming...';
  try {
    const response = await fetch('/api/v1/auth/verify-email', {
      method: 'POST', credentials: 'omit',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token})
    });
    const data = await response.json();
    if (!response.ok) {
      status.textContent = typeof data.detail === 'string' ? data.detail :
        'Verification failed. Request a new email in the app.';
      button.disabled = false;
      return;
    }
    token = null;
    status.textContent = 'Email confirmed. Return to DAHLIA and click Check verification status in Profile.';
    button.textContent = 'Email confirmed';
  } catch {
    status.textContent = 'Could not reach the server. Please try again.';
    button.disabled = false;
  }
});
</script></body></html>""".replace("__NONCE__", nonce)
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; connect-src 'self'; "
            f"script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        ),
    })

"""Static reset password page; opening the link alone never changes the password."""

import secrets
from fastapi.responses import HTMLResponse


def reset_password_page() -> HTMLResponse:
    nonce = secrets.token_urlsafe(24)
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>DAHLIA Password Reset</title>
<style>
body{font:16px system-ui,sans-serif;background:#f7f7f5;color:#222;margin:10vh auto;padding:24px;max-width:480px}
h1{font-size:22px;margin-bottom:4px}
h2{font-size:16px;font-weight:400;color:#666;margin-top:0;margin-bottom:24px}
.field{margin-bottom:16px}
label{display:block;font-size:13px;font-weight:600;margin-bottom:6px;color:#444}
input{width:100%;box-sizing:border-box;padding:10px 12px;font:inherit;border:1px solid #ccc;border-radius:6px}
button{width:100%;font:inherit;font-weight:600;padding:12px;background:#6B5DD3;color:#fff;border:none;border-radius:6px;cursor:pointer;margin-top:8px}
button:disabled{background:#999;cursor:not-allowed}
#status{margin-top:16px;font-size:14px;line-height:1.5}
.success{color:#25845d;font-weight:600}
.error{color:#c93f4b;font-weight:600}
</style></head>
<body><h1>DAHLIA</h1><h2>Choose a new password</h2>
<div id="form-container">
  <div class="field">
    <label for="pwd">New password (minimum 8 characters)</label>
    <input id="pwd" type="password" minlength="8" required />
  </div>
  <div class="field">
    <label for="pwd_confirm">Confirm new password</label>
    <input id="pwd_confirm" type="password" minlength="8" required />
  </div>
  <button id="submit-btn" type="button">Reset password</button>
</div>
<p id="status"></p>
<script nonce="__NONCE__">
const params = new URLSearchParams(window.location.hash.slice(1));
let token = params.get('token');
history.replaceState(null, '', window.location.pathname);
const status = document.getElementById('status');
const button = document.getElementById('submit-btn');
const pwd = document.getElementById('pwd');
const pwdConfirm = document.getElementById('pwd_confirm');
const formContainer = document.getElementById('form-container');

if (!token) {
  status.textContent = 'Invalid link. Please open the full link from your reset email.';
  status.className = 'error';
  button.disabled = true;
}

button.addEventListener('click', async () => {
  const p1 = pwd.value;
  const p2 = pwdConfirm.value;
  if (!p1 || p1.length < 8) {
    status.textContent = 'Password must be at least 8 characters long.';
    status.className = 'error';
    return;
  }
  if (p1 !== p2) {
    status.textContent = 'Passwords do not match.';
    status.className = 'error';
    return;
  }
  button.disabled = true;
  status.textContent = 'Resetting password...';
  status.className = '';
  try {
    const response = await fetch('/api/v1/auth/reset-password', {
      method: 'POST',
      credentials: 'omit',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token: token, new_password: p1})
    });
    const data = await response.json();
    if (!response.ok) {
      status.textContent = typeof data.detail === 'string' ? data.detail : 'Password reset failed. Request a new link.';
      status.className = 'error';
      button.disabled = false;
      return;
    }
    token = null;
    formContainer.style.display = 'none';
    status.textContent = 'Password has been successfully reset! You can now log in using the DAHLIA desktop application.';
    status.className = 'success';
  } catch {
    status.textContent = 'Could not reach the server. Please try again.';
    status.className = 'error';
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


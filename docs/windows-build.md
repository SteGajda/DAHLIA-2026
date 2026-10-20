# Windows EXE build

Run from the repository root on Windows with 64-bit Python 3.12 already in
`.venv`. Close any old DAHLIA EXE before rebuilding.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\frontend\scripts\build_windows.ps1
```

This policy applies only to that child PowerShell process. It does not change
the machine's persistent execution policy.

Output: `frontend/dist/DAHLIA-1.1.0-win-x64.exe` for the current project version.
The name follows the version in frontend/pyproject.toml. Rebuilding the same
version replaces that EXE. The public Azure API URL and a 120-second timeout
are included, so no PowerShell environment setup is needed on the recipient's
computer. Explicit DAHLIA_API_URL/DAHLIA_API_TIMEOUT environment overrides still
take priority. There is no automatic update of an already distributed EXE.

The script uses an isolated ignored `.venv-build` at the repository root and
installs frontend build dependencies there. It invokes `python -m PyInstaller`
with explicit data and module collection, including dynamic UMAP/Numba/LLVM and
Windows keyring modules. It does not package the backend directory, .env, SQL
credentials, SMTP password or JWT secret. The CSV is application input required
for local experiments. Build staging and generated specs live under
frontend/build/windows; output is ignored under frontend/dist.

The script retains compatible installed dependency versions between builds;
it is repeatable but not a fully locked bit-for-bit reproducible build. Alongside
the EXE it writes public build information, SHA256 and dependency versions for
diagnosis. Only the EXE is required for normal distribution.

After frontend changes, run the same command again. Code does not need to be
committed for the build to include it. Keep a copy of an old EXE elsewhere if
you want to retain it. To show a different release version, update the version
in frontend/pyproject.toml and APP_VERSION in frontend/src/dahlia/services/config.py
consistently before building.

Backend changes require a new Docker image and Azure deployment separately.
Building the EXE alone does not deploy server changes. Local experiment history
is not inside the EXE and remains under `%APPDATA%/DAHLIA/dahlia_local.db`.

## Run and verify

```powershell
& .\frontend\dist\DAHLIA-1.1.0-win-x64.exe
```

Check startup, PCA/t-SNE/UMAP, a completed experiment, local save, cloud login,
verified-email state and manual synchronization. Test on another Windows
computer without Python. The native window uses Microsoft Edge WebView2
Runtime; install it if absent. One-file builds extract native libraries at
startup, so initial launch may take time and the package may be large.

Startup logs for a windowed EXE: `%APPDATA%/DAHLIA/logs/desktop.log`.
If needed, build a separate diagnostic EXE with a console:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\frontend\scripts\build_windows.ps1 -Console
```

The diagnostic name ends in `-console.exe` and does not overwrite the standard
EXE. A missing output file or failed subprocess stops the build; do not treat
an older EXE remaining from a failed build as newly generated.

## Sources

- https://nicegui.io/documentation/section_configuration_deployment
- https://pyinstaller.org/en/stable/usage.html
- https://pywebview.flowrl.com/guide/installation

Python bootstrap behavior can be tested on Linux. A Windows executable must be
built and run on Windows; cross-platform unit tests are not proof that its
native window starts on a clean Windows installation.

[CmdletBinding()]
param(
    [string]$ApiUrl = "https://dahlia-api.lemonwave-82fa477c.germanywestcentral.azurecontainerapps.io",
    [ValidateRange(1, 600)][int]$ApiTimeout = 120,
    [switch]$Console
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Program,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )
    & $Program @ArgumentList
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Program" }
}

if ($env:OS -ne "Windows_NT") { throw "Build the Windows executable on Windows." }
$api = [Uri]$ApiUrl
$localHttp = $api.Scheme -eq "http" -and $api.IsLoopback
if (-not $api.IsAbsoluteUri -or ($api.Scheme -ne "https" -and -not $localHttp) -or
    $api.UserInfo -or $api.Query -or $api.Fragment -or $api.AbsolutePath -ne "/") {
    throw "ApiUrl must be an HTTPS origin (HTTP is allowed on localhost)."
}

$FrontendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepositoryRoot = Split-Path -Parent $FrontendRoot
$BuildEnvironment = Join-Path $RepositoryRoot ".venv-build"
$BuildPython = Join-Path $BuildEnvironment "Scripts\python.exe"
$SourcePython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$PackCommand = $BuildPython
$BuildRoot = Join-Path $FrontendRoot "build\windows"
$DistRoot = Join-Path $FrontendRoot "dist"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

Push-Location $FrontendRoot
try {
    if (-not (Test-Path $BuildPython)) {
        if (-not (Test-Path $SourcePython)) { throw "Missing .venv\Scripts\python.exe in the repository root." }
        Invoke-Checked $SourcePython @("-m", "venv", $BuildEnvironment)
    }
    Invoke-Checked $BuildPython @(
        "-c", "import sys, struct; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8, 'Use 64-bit Python 3.12 for this build'"
    )
    # Frontend-only environment. Compatible versions are retained on later builds.
    Invoke-Checked $BuildPython @("-m", "pip", "install", "-e", ".[build]")
    Invoke-Checked $BuildPython @("-m", "pip", "check")

    $AppVersion = & $BuildPython -c "import pathlib, tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])"
    if ($LASTEXITCODE -ne 0) { throw "Cannot read the application version." }
    $AppVersion = $AppVersion.Trim()
    if ($AppVersion -notmatch '^[0-9A-Za-z._+-]+$') { throw "Unexpected application version." }
    $ArtifactName = "DAHLIA-$AppVersion-win-x64"
    if ($Console) { $ArtifactName += "-console" }
    $ArtifactPath = Join-Path $DistRoot "$ArtifactName.exe"

    if (Test-Path $ArtifactPath) {
        # Fail if the old EXE is still open instead of reporting a stale build.
        $stream = [System.IO.File]::Open($ArtifactPath, 'Open', 'ReadWrite', 'None')
        $stream.Dispose()
    }
    New-Item -ItemType Directory -Force -Path $BuildRoot, $DistRoot | Out-Null
    $RuntimeConfig = Join-Path $BuildRoot "dahlia_build.json"
    $config = @{
        api_url = $ApiUrl.TrimEnd('/')
        api_timeout = $ApiTimeout
        built_at_utc = [DateTime]::UtcNow.ToString("o")
        app_version = $AppVersion
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText($RuntimeConfig, $config, $Utf8)

    $PackArguments = @(
        "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile", "--noupx",
        "--name", $ArtifactName,
        "--distpath", $DistRoot,
        "--workpath", (Join-Path $BuildRoot "work"),
        "--specpath", $BuildRoot,
        "--paths", (Join-Path $FrontendRoot "src"),
        "--add-data", ((Join-Path $FrontendRoot "data") + ";data"),
        "--add-data", ($RuntimeConfig + ";."),
        "--collect-all", "nicegui",
        "--collect-all", "dahlia",
        "--collect-all", "umap",
        "--collect-all", "pynndescent",
        "--collect-all", "numba",
        "--collect-all", "llvmlite",
        "--collect-all", "keyring",
        "--hidden-import", "keyring.backends.Windows",
        "--copy-metadata", "dahlia"
    )
    if (-not $Console) { $PackArguments += "--windowed" }
    $PackArguments += (Join-Path $FrontendRoot "run_app.py")
    Invoke-Checked $PackCommand $PackArguments
    if (-not (Test-Path $ArtifactPath)) { throw "Build ended without the expected EXE." }

    $hash = (Get-FileHash $ArtifactPath -Algorithm SHA256).Hash
    $requirements = & $BuildPython -m pip freeze
    if ($LASTEXITCODE -ne 0) { throw "Cannot save dependency versions." }
    [System.IO.File]::WriteAllLines(
        (Join-Path $DistRoot "$ArtifactName.requirements.txt"), [string[]]$requirements, $Utf8
    )
    $buildInfo = @{
        app_version = $AppVersion
        built_at_utc = [DateTime]::UtcNow.ToString("o")
        api_url = $ApiUrl.TrimEnd('/')
        sha256 = $hash
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText(
        (Join-Path $DistRoot "$ArtifactName.build.json"), $buildInfo, $Utf8
    )
    Write-Host ""
    Write-Host "Build completed: $ArtifactPath"
    Write-Host "API: $($ApiUrl.TrimEnd('/'))"
    Write-Host "SHA256: $hash"
}
finally { Pop-Location }

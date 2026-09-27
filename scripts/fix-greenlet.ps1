<#
.SYNOPSIS
    Repair a backend virtualenv where importing greenlet fails with
    "An Application Control policy has blocked this file."

.DESCRIPTION
    SQLAlchemy's async engine requires greenlet, which ships a compiled
    extension (_greenlet...pyd). On machines with Windows Smart App Control or
    WDAC enabled, a freshly downloaded unsigned .pyd is blocked even though the
    same package installed into your *system* Python is allowed. The result is
    that `pip install -r requirements.txt` succeeds and then
    `import sqlalchemy.ext.asyncio` fails at runtime.

    This script copies the already-trusted greenlet from your system Python
    into the venv, which is what makes the venv work on such a machine.

    It changes nothing about the application code.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\fix-greenlet.ps1
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvSite = Join-Path $root "backend\.venv\Lib\site-packages"

if (-not (Test-Path $venvSite)) {
    Write-Error "No venv found at backend\.venv - create it first: python -m venv backend\.venv"
}

# Where is greenlet installed for the interpreter that is NOT blocked?
$sysGreenlet = (python -c "import greenlet, os; print(os.path.dirname(greenlet.__file__))" 2>$null)
if (-not $sysGreenlet -or -not (Test-Path $sysGreenlet)) {
    Write-Error "Could not locate a working greenlet in your system Python. Install it there first: python -m pip install greenlet"
}

Write-Host "Trusted greenlet found at: $sysGreenlet" -ForegroundColor Cyan

$target = Join-Path $venvSite "greenlet"
if (Test-Path $target) {
    Write-Host "Removing the blocked copy from the venv..." -ForegroundColor Yellow
    try {
        Remove-Item -Recurse -Force $target -ErrorAction Stop
        Get-ChildItem $venvSite -Filter "greenlet-*" -Directory -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    } catch {
        # Almost always a running uvicorn holding the loaded .pyd open.
        Write-Error "Could not replace greenlet: the file is locked. Stop any running API (uvicorn) and re-run this script."
    }
}

Copy-Item -Recurse -Force $sysGreenlet $target
Write-Host "Copied greenlet into the venv." -ForegroundColor Green

$venvPython = Join-Path $root "backend\.venv\Scripts\python.exe"
$probe = "import greenlet; from sqlalchemy.ext.asyncio import create_async_engine; " +
         "print('OK  greenlet', greenlet.__version__, '- sqlalchemy asyncio importable')"

& $venvPython -c $probe
if ($LASTEXITCODE -ne 0) {
    Write-Error "Still failing. The policy may be path-based: try creating the venv outside your Documents folder, or install greenlet from source if you have a C compiler."
}
Write-Host ""
Write-Host "Now start the API:  backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload" -ForegroundColor Green

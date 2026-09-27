<#
.SYNOPSIS
    Start the AapaatSathi API and web app together, first-run safe.

.DESCRIPTION
    Creates the Python venv and installs backend dependencies if they are
    missing, runs npm install if node_modules is missing, then starts both
    processes. Press Ctrl+C to stop both.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
#>

[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPy = Join-Path $backend ".venv\Scripts\python.exe"

function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

if (-not (Test-Cmd "python")) { Write-Error "Python 3.11+ is required and was not found on PATH." }
if (-not (Test-Cmd "node"))   { Write-Error "Node 18+ is required and was not found on PATH." }

if (-not (Test-Path $venvPy)) {
    Write-Host "Creating backend virtualenv..." -ForegroundColor Cyan
    python -m venv (Join-Path $backend ".venv")
    & $venvPy -m pip install --upgrade pip --quiet
    & $venvPy -m pip install -r (Join-Path $backend "requirements.txt")
}

$nodeModules = Join-Path $frontend "node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location $frontend
    npm install --no-audit --no-fund
    Pop-Location
}

Write-Host "`nStarting API on http://127.0.0.1:$ApiPort (docs at /docs)" -ForegroundColor Green
$api = Start-Process -PassThru -WindowStyle Normal -FilePath $venvPy `
    -ArgumentList "-m","uvicorn","app.main:app","--reload","--host","127.0.0.1","--port",$ApiPort `
    -WorkingDirectory $backend

Write-Host "Starting web on http://localhost:$WebPort`n" -ForegroundColor Green
$web = Start-Process -PassThru -WindowStyle Normal -FilePath "cmd.exe" `
    -ArgumentList "/c","npm run dev -- --port $WebPort" -WorkingDirectory $frontend

Write-Host "Both running. Open http://localhost:$WebPort  ·  Ctrl+C here to stop." -ForegroundColor Yellow
Write-Host "API smoke test:  $venvPy scripts\smoke_test.py --base http://127.0.0.1:$ApiPort"

try {
    Wait-Process -Id $api.Id,$web.Id
} finally {
    Stop-Process -Id $api.Id,$web.Id -Force -ErrorAction SilentlyContinue
    Write-Host "`nStopped." -ForegroundColor Cyan
}

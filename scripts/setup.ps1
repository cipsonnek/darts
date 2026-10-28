# One-time setup on a new Windows PC:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Creates .venv, installs the Python packages, installs and builds the web frontend.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "Missing: $cmd. $hint" -ForegroundColor Red
        exit 1
    }
}

Need "python" "Install Python 3.10-3.12 from python.org (tick 'Add python.exe to PATH')."
Need "npm" "Install Node.js 20 LTS or newer from nodejs.org."

# Take the last "X.Y" line: python may print other lines first (startup warnings, Store alias).
$pyout = @(& python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>&1 | ForEach-Object { "$_" })
$pyver = $pyout | Where-Object { $_ -match '^\d+\.\d+$' } | Select-Object -Last 1
if (-not $pyver) {
    Write-Host "Could not run Python. It printed:" -ForegroundColor Red
    $pyout | ForEach-Object { Write-Host "  $_" }
    Write-Host "Install Python 3.12 from python.org (tick 'Add python.exe to PATH'), then open a new PowerShell." -ForegroundColor Red
    exit 1
}
Write-Host "Python $pyver, Node $(& node --version)"
if ([version]$pyver -lt [version]"3.10") { Write-Host "Python 3.10 or newer is required." -ForegroundColor Red; exit 1 }

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    & python -m venv .venv
}
& .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
Write-Host "Installing Python packages (a few minutes)..."
& .venv\Scripts\python.exe -m pip install -e ".[dev]" --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "Installing and building the web frontend..."
Push-Location frontend
& npm ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
& npm run build
if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
Pop-Location

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  Real cameras:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1"
Write-Host "  Simulator:     powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Simulator"
Write-Host "Then open http://localhost:8000"

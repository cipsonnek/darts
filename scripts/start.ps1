# Start DartSense:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Simulator] [-Lan]
#   -Simulator  use three synthetic cameras instead of real ones
#   -Lan        listen on all network interfaces (open the UI from a phone/tablet/TV)
param([switch]$Simulator, [switch]$Lan)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Run scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}
# After "git pull": rebuild the web UI when its sources are newer than the built copy.
$dist = "frontend\dist\index.html"
$src = Get-ChildItem frontend\src, frontend\index.html, frontend\package.json -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ((Get-Command npm -ErrorAction SilentlyContinue) -and (-not (Test-Path $dist) -or ($src -and $src.LastWriteTime -gt (Get-Item $dist).LastWriteTime))) {
    Write-Host "Updating the web UI (npm run build)..."
    Push-Location frontend
    $lock = Get-Item package-lock.json -ErrorAction SilentlyContinue
    $installed = Get-Item node_modules\.package-lock.json -ErrorAction SilentlyContinue
    if (-not $installed -or ($lock -and $lock.LastWriteTime -gt $installed.LastWriteTime)) { & npm ci --no-audit --no-fund }
    & npm run build
    if ($LASTEXITCODE -ne 0) { Write-Host "UI build failed - starting with the previous UI." -ForegroundColor Yellow }
    Pop-Location
}
$pyArgs = @("-m", "backend")
if ($Simulator) { $pyArgs += "--simulator" }
if ($Lan) { $pyArgs += @("--host", "0.0.0.0") }
Write-Host "Starting DartSense on http://localhost:8000  (Ctrl+C to stop)"
& .venv\Scripts\python.exe @pyArgs

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
$pyArgs = @("-m", "backend")
if ($Simulator) { $pyArgs += "--simulator" }
if ($Lan) { $pyArgs += @("--host", "0.0.0.0") }
Write-Host "Starting DartSense on http://localhost:8000  (Ctrl+C to stop)"
& .venv\Scripts\python.exe @pyArgs

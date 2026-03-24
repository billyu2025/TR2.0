# Restart TR-Backend service with administrator privileges
# Run this script as Administrator

Write-Host "Stopping TR-Backend service..." -ForegroundColor Yellow
Stop-Service TR-Backend -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

Write-Host "Clearing Python cache..." -ForegroundColor Yellow
$backendPath = "C:\TR-master\TR UI\backend"
Get-ChildItem -Path $backendPath -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $backendPath -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Starting TR-Backend service..." -ForegroundColor Yellow
Start-Service TR-Backend -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$service = Get-Service TR-Backend -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "Service Status: $($service.Status)" -ForegroundColor $(if ($service.Status -eq 'Running') { 'Green' } else { 'Red' })
} else {
    Write-Host "Service not found!" -ForegroundColor Red
}

Write-Host "`nChecking latest logs..." -ForegroundColor Yellow
$logFile = Join-Path $backendPath "logs\app.log"
if (Test-Path $logFile) {
    Get-Content $logFile -Tail 10 | Write-Host
}

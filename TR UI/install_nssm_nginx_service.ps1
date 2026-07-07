# Install TR-Nginx Windows service via NSSM (auto-start on boot).
# Run as Administrator:
#   cd "C:\TR-master\TR UI"
#   .\install_nssm_nginx_service.ps1
# Reinstall: .\install_nssm_nginx_service.ps1 -Force

param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: Administrator privileges required." -ForegroundColor Red
    Write-Host "Right-click PowerShell and choose Run as administrator." -ForegroundColor Yellow
    exit 1
}

$uiDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$nginxDir = Join-Path $uiDir "nginx-1.28.0"
$nginxExe = Join-Path $nginxDir "nginx.exe"
$nginxWrapper = Join-Path $nginxDir "start_nginx_service.bat"
$logDir = Join-Path $nginxDir "logs"
$backendNssm = Join-Path $uiDir "backend\nssm-2.24"
$arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
$nssmExe = Join-Path (Join-Path $backendNssm $arch) "nssm.exe"
$serviceName = "TR-Nginx"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TR Nginx NSSM Service Install" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $nginxExe)) {
    Write-Host "ERROR: nginx.exe not found: $nginxExe" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $nginxWrapper)) {
    Write-Host "ERROR: wrapper not found: $nginxWrapper" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $nssmExe)) {
    Write-Host "ERROR: nssm.exe not found: $nssmExe" -ForegroundColor Red
    Write-Host "Run backend\install_nssm_service.ps1 first to download NSSM." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

Write-Host "[1/5] Stop any manually started nginx..." -ForegroundColor Yellow
$nginxProcs = Get-Process nginx -ErrorAction SilentlyContinue
if ($nginxProcs) {
    try {
        & $nginxExe -c conf\nginx.conf -s quit 2>$null
        Start-Sleep -Seconds 2
    } catch { }
    $remaining = Get-Process nginx -ErrorAction SilentlyContinue
    if ($remaining) {
        $remaining | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    Write-Host "Stopped manual nginx processes." -ForegroundColor Green
} else {
    Write-Host "No nginx process running." -ForegroundColor Green
}
Write-Host ""

Write-Host "[2/5] Check existing service $serviceName ..." -ForegroundColor Yellow
$existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existing) {
    if (-not $Force) {
        Write-Host "Service already exists. Use -Force to reinstall." -ForegroundColor Yellow
        Write-Host "  Get-Service TR-Nginx" -ForegroundColor White
        exit 0
    }
    if ($existing.Status -eq 'Running' -or $existing.Status -eq 'Paused') {
        Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    & $nssmExe remove $serviceName confirm
    Start-Sleep -Seconds 1
    Write-Host "Removed old service." -ForegroundColor Green
}
Write-Host ""

Write-Host "[3/5] Install NSSM service..." -ForegroundColor Yellow
& $nssmExe install $serviceName $nginxWrapper
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: nssm install failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}
& $nssmExe set $serviceName Application $nginxWrapper
& $nssmExe set $serviceName AppDirectory $nginxDir
& $nssmExe set $serviceName DisplayName "TR Report System Nginx"
& $nssmExe set $serviceName Description "TR Report System frontend (Nginx port 8000)"
& $nssmExe set $serviceName Start SERVICE_AUTO_START
& $nssmExe set $serviceName AppStdout (Join-Path $logDir "nssm_stdout.log")
& $nssmExe set $serviceName AppStderr (Join-Path $logDir "nssm_stderr.log")
& $nssmExe set $serviceName AppRotateFiles 1
& $nssmExe set $serviceName AppRotateOnline 1
& $nssmExe set $serviceName AppRotateSeconds 86400
& $nssmExe set $serviceName AppRotateBytes 10485760
& $nssmExe set $serviceName AppExit Default Restart
& $nssmExe set $serviceName AppRestartDelay 5000
& $nssmExe set $serviceName AppThrottle 1500
& $nssmExe set $serviceName AppStopMethodSkip 0
& $nssmExe set $serviceName AppStopMethodConsole 1500
& $nssmExe set $serviceName AppStopMethodWindow 1500
& $nssmExe set $serviceName AppStopMethodThreads 1500
Write-Host "Service registered." -ForegroundColor Green
Write-Host ""

Write-Host "[4/5] Start service..." -ForegroundColor Yellow
try {
    Start-Service -Name $serviceName
    Start-Sleep -Seconds 3
} catch {
    Write-Host "Start failed: $_" -ForegroundColor Red
    Write-Host "Check log: $logDir\nssm_stderr.log" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

Write-Host "[5/5] Verify..." -ForegroundColor Yellow
$svc = Get-Service -Name $serviceName
$color = if ($svc.Status -eq 'Running') { 'Green' } else { 'Yellow' }
Write-Host "  Status: $($svc.Status)  StartType: $($svc.StartType)" -ForegroundColor $color
$port8000 = netstat -ano | Select-String ":8000" | Select-String "LISTENING"
if ($port8000) {
    Write-Host "  Port 8000: LISTENING" -ForegroundColor Green
} else {
    Write-Host "  WARNING: port 8000 not listening. Check nginx error.log" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Done. Nginx will auto-start after reboot." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Commands:" -ForegroundColor Cyan
Write-Host "  Start-Service TR-Nginx" -ForegroundColor White
Write-Host "  Stop-Service TR-Nginx" -ForegroundColor White
Write-Host "  Restart-Service TR-Nginx" -ForegroundColor White
Write-Host "  Get-Service TR-Nginx" -ForegroundColor White
Write-Host ""

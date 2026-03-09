# 启动 NSSM 服务脚本
# 使用方法：以管理员身份运行 PowerShell，然后执行：.\start_nssm_service.ps1

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "错误：此脚本需要管理员权限！" -ForegroundColor Red
    Write-Host "请以管理员身份运行 PowerShell，然后重新执行此脚本。" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "启动 TR Backend 服务" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 设置路径
$backendDir = "C:\TR-master\TR UI\backend"
$nssmPath = Join-Path $backendDir "nssm-2.24\win64\nssm.exe"
$serviceName = "TR-Backend"

# 检查 NSSM 是否存在
if (-not (Test-Path $nssmPath)) {
    Write-Host "错误：NSSM 未找到: $nssmPath" -ForegroundColor Red
    Write-Host "请确保 NSSM 已解压到正确位置" -ForegroundColor Yellow
    pause
    exit 1
}

# 检查服务是否存在
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "错误：服务 '$serviceName' 不存在！" -ForegroundColor Red
    Write-Host "请先运行 install_nssm_service.ps1 安装服务" -ForegroundColor Yellow
    pause
    exit 1
}

# 检查服务状态
Write-Host "当前服务状态: $($service.Status)" -ForegroundColor Yellow

if ($service.Status -eq 'Running') {
    Write-Host "服务已在运行中" -ForegroundColor Green
} else {
    Write-Host "正在启动服务..." -ForegroundColor Yellow
    try {
        Start-Service -Name $serviceName
        Start-Sleep -Seconds 3
        
        $service = Get-Service -Name $serviceName
        if ($service.Status -eq 'Running') {
            Write-Host "服务启动成功！" -ForegroundColor Green
        } else {
            Write-Host "警告：服务状态: $($service.Status)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "错误：启动服务失败: $_" -ForegroundColor Red
        Write-Host "请查看错误日志: $(Join-Path $backendDir 'logs\nssm_error.log')" -ForegroundColor Yellow
        pause
        exit 1
    }
}

# 验证服务
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "服务信息" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Get-Service $serviceName | Format-List Name, DisplayName, Status, StartType

# 检查端口
Write-Host ""
Write-Host "检查端口 5000..." -ForegroundColor Yellow
$portCheck = netstat -ano | Select-String ":5000" | Select-String "LISTENING"
if ($portCheck) {
    Write-Host "端口 5000 正在监听" -ForegroundColor Green
} else {
    Write-Host "警告：端口 5000 未监听，服务可能未正常启动" -ForegroundColor Yellow
    Write-Host "请查看日志: $(Join-Path $backendDir 'logs\nssm_error.log')" -ForegroundColor Yellow
}

# 测试 API
Write-Host ""
Write-Host "测试 API..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "API 响应正常" -ForegroundColor Green
} catch {
    Write-Host "警告：API 无响应，请检查服务日志" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "完成！" -ForegroundColor Green
Write-Host ""
Write-Host "常用命令：" -ForegroundColor Cyan
Write-Host "  启动:   Start-Service TR-Backend" -ForegroundColor White
Write-Host "  停止:   Stop-Service TR-Backend" -ForegroundColor White
Write-Host "  重启:   Restart-Service TR-Backend" -ForegroundColor White
Write-Host "  状态:   Get-Service TR-Backend" -ForegroundColor White
Write-Host ""

pause

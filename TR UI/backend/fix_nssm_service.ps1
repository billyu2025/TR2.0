# 修复和启动 NSSM 服务脚本
# 使用方法：以管理员身份运行 PowerShell，然后执行：.\fix_nssm_service.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "修复和启动 TR Backend 服务" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

cd "C:\TR-master\TR UI\backend"

# 检查服务是否存在
$service = Get-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "❌ 服务不存在，需要先安装" -ForegroundColor Red
    Write-Host "运行: .\install_nssm_service.ps1" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "当前服务状态: $($service.Status)" -ForegroundColor Yellow
Write-Host ""

# 根据状态处理
switch ($service.Status) {
    "Paused" {
        Write-Host "服务处于暂停状态，正在恢复..." -ForegroundColor Yellow
        try {
            Resume-Service -Name "TR-Backend"
            Start-Sleep -Seconds 2
            $service = Get-Service -Name "TR-Backend"
            if ($service.Status -eq 'Running') {
                Write-Host "✅ 服务已恢复运行" -ForegroundColor Green
            } else {
                Write-Host "⚠️ 恢复失败，尝试重启..." -ForegroundColor Yellow
                Restart-Service -Name "TR-Backend"
            }
        } catch {
            Write-Host "恢复失败，尝试重启..." -ForegroundColor Yellow
            Restart-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
        }
    }
    "Stopped" {
        Write-Host "服务已停止，正在启动..." -ForegroundColor Yellow
        try {
            Start-Service -Name "TR-Backend"
            Start-Sleep -Seconds 3
        } catch {
            Write-Host "❌ 启动失败: $_" -ForegroundColor Red
            Write-Host "查看错误日志..." -ForegroundColor Yellow
            if (Test-Path "logs\nssm_error.log") {
                Write-Host "最近的错误：" -ForegroundColor Yellow
                Get-Content "logs\nssm_error.log" -Tail 20
            }
            pause
            exit 1
        }
    }
    "Running" {
        Write-Host "✅ 服务已在运行" -ForegroundColor Green
    }
    default {
        Write-Host "服务状态异常: $($service.Status)" -ForegroundColor Yellow
        Write-Host "尝试重启服务..." -ForegroundColor Yellow
        Restart-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
    }
}

# 等待服务稳定
Start-Sleep -Seconds 2

# 检查最终状态
$service = Get-Service -Name "TR-Backend"
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "服务状态" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "状态: $($service.Status)" -ForegroundColor $(if ($service.Status -eq 'Running') { 'Green' } else { 'Yellow' })
Write-Host ""

# 检查端口
Write-Host "检查端口 5000..." -ForegroundColor Yellow
$port = netstat -ano | Select-String ":5000" | Select-String "LISTENING"
if ($port) {
    Write-Host "✅ 端口 5000 正在监听" -ForegroundColor Green
} else {
    Write-Host "❌ 端口 5000 未监听" -ForegroundColor Red
    Write-Host "查看错误日志..." -ForegroundColor Yellow
    if (Test-Path "logs\nssm_error.log") {
        Get-Content "logs\nssm_error.log" -Tail 20
    }
}

# 测试 API
if ($service.Status -eq 'Running') {
    Write-Host ""
    Write-Host "测试 API..." -ForegroundColor Yellow
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Write-Host "✅ API 响应正常" -ForegroundColor Green
    } catch {
        Write-Host "⚠️ API 无响应: $_" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "完成！" -ForegroundColor Green
Write-Host ""
pause

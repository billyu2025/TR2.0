# 强制停止 TR-Backend 服务和相关进程
# 需要以管理员身份运行

Write-Host "正在停止 TR-Backend 服务..." -ForegroundColor Yellow

# 方法1: 使用 NSSM 停止服务
$nssmExe = Join-Path $PSScriptRoot "nssm-2.24\win64\nssm.exe"
if (Test-Path $nssmExe) {
    Write-Host "尝试使用 NSSM 停止服务..." -ForegroundColor Cyan
    & $nssmExe stop TR-Backend 2>&1 | Out-Null
    Start-Sleep -Seconds 3
}

# 方法2: 使用 sc 停止服务
Write-Host "尝试使用 sc 停止服务..." -ForegroundColor Cyan
sc stop TR-Backend 2>&1 | Out-Null
Start-Sleep -Seconds 3

# 方法3: 查找并关闭占用端口 5000 的进程
Write-Host "查找占用端口 5000 的进程..." -ForegroundColor Cyan
$port5000 = netstat -ano | Select-String ":5000" | Select-String "LISTENING"
if ($port5000) {
    $pid = ($port5000 -split '\s+')[-1]
    if ($pid -match '^\d+$') {
        Write-Host "找到进程 PID: $pid" -ForegroundColor Yellow
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "已成功终止进程 $pid" -ForegroundColor Green
        } catch {
            Write-Host "无法终止进程 $pid，可能需要管理员权限" -ForegroundColor Red
            Write-Host "请手动运行: taskkill /F /PID $pid" -ForegroundColor Yellow
        }
    }
}

# 等待进程完全退出
Start-Sleep -Seconds 2

# 再次检查端口
$portCheck = netstat -ano | Select-String ":5000" | Select-String "LISTENING"
if ($portCheck) {
    Write-Host "警告: 端口 5000 仍被占用" -ForegroundColor Red
    Write-Host "请以管理员身份运行以下命令:" -ForegroundColor Yellow
    Write-Host "  taskkill /F /PID $pid" -ForegroundColor Yellow
} else {
    Write-Host "端口 5000 已释放" -ForegroundColor Green
}

# 检查服务状态
$service = Get-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "服务状态: $($service.Status)" -ForegroundColor Cyan
} else {
    Write-Host "未找到 TR-Backend 服务" -ForegroundColor Yellow
}

Write-Host "`n完成！" -ForegroundColor Green

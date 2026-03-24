# 完整强制重启脚本 - 需要以管理员身份运行
# 此脚本会：
# 1. 停止服务
# 2. 关闭占用端口 5000 的进程
# 3. 清理所有 Python 缓存
# 4. 重新启动服务

param(
    [switch]$SkipStop = $false
)

$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TR-Backend 完整重启脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not $SkipStop) {
    Write-Host "[1/4] 停止服务和进程..." -ForegroundColor Yellow
    
    # 停止 NSSM 服务
    $nssmExe = Join-Path $PSScriptRoot "nssm-2.24\win64\nssm.exe"
    if (Test-Path $nssmExe) {
        Write-Host "  停止 NSSM 服务..." -ForegroundColor Gray
        & $nssmExe stop TR-Backend 2>&1 | Out-Null
        Start-Sleep -Seconds 2
    }
    
    # 停止 Windows 服务
    Write-Host "  停止 Windows 服务..." -ForegroundColor Gray
    $service = Get-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
    if ($service -and $service.Status -eq 'Running') {
        Stop-Service -Name "TR-Backend" -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    
    # 关闭占用端口 5000 的进程
    Write-Host "  查找并关闭占用端口 5000 的进程..." -ForegroundColor Gray
    $portInfo = netstat -ano | Select-String ":5000.*LISTENING"
    if ($portInfo) {
        $parts = $portInfo -split '\s+'
        $pid = $parts[-1]
        if ($pid -match '^\d+$') {
            Write-Host "    找到进程 PID: $pid" -ForegroundColor Yellow
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-Host "    ✓ 已终止进程 $pid" -ForegroundColor Green
            } catch {
                Write-Host "    ✗ 无法终止进程 $pid (可能需要管理员权限)" -ForegroundColor Red
                Write-Host "    请手动运行: taskkill /F /PID $pid" -ForegroundColor Yellow
            }
        }
    }
    
    # 等待进程完全退出
    Start-Sleep -Seconds 3
    
    Write-Host "  ✓ 停止完成" -ForegroundColor Green
    Write-Host ""
}

# 清理缓存
Write-Host "[2/4] 清理 Python 缓存..." -ForegroundColor Yellow
$cacheCleared = $false

# 清理 .pyc 文件
$pycFiles = Get-ChildItem -Path $PSScriptRoot -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue
if ($pycFiles) {
    $pycFiles | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "  ✓ 已清理 .pyc 文件" -ForegroundColor Gray
    $cacheCleared = $true
}

# 清理 __pycache__ 目录
$pycacheDirs = Get-ChildItem -Path $PSScriptRoot -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue
if ($pycacheDirs) {
    $pycacheDirs | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  ✓ 已清理 __pycache__ 目录" -ForegroundColor Gray
    $cacheCleared = $true
}

if (-not $cacheCleared) {
    Write-Host "  ✓ 没有找到缓存文件" -ForegroundColor Gray
}

Write-Host "  ✓ 缓存清理完成" -ForegroundColor Green
Write-Host ""

# 验证端口已释放
Write-Host "[3/4] 验证端口状态..." -ForegroundColor Yellow
$portCheck = netstat -ano | Select-String ":5000.*LISTENING"
if ($portCheck) {
    Write-Host "  ⚠ 警告: 端口 5000 仍被占用" -ForegroundColor Red
    $parts = $portCheck -split '\s+'
    $pid = $parts[-1]
    Write-Host "    请手动运行: taskkill /F /PID $pid" -ForegroundColor Yellow
    Write-Host "    然后重新运行此脚本" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "  ✓ 端口 5000 已释放" -ForegroundColor Green
}
Write-Host ""

# 启动服务
Write-Host "[4/4] 启动服务..." -ForegroundColor Yellow
$nssmExe = Join-Path $PSScriptRoot "nssm-2.24\win64\nssm.exe"
if (Test-Path $nssmExe) {
    Write-Host "  使用 NSSM 启动服务..." -ForegroundColor Gray
    $result = & $nssmExe start TR-Backend 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 服务启动命令已发送" -ForegroundColor Green
    } else {
        Write-Host "  ✗ 服务启动失败: $result" -ForegroundColor Red
    }
} else {
    Write-Host "  ✗ 未找到 NSSM 可执行文件" -ForegroundColor Red
    exit 1
}

# 等待服务启动
Start-Sleep -Seconds 5

# 检查服务状态
Write-Host ""
Write-Host "检查服务状态..." -ForegroundColor Cyan
$status = & $nssmExe status TR-Backend 2>&1
Write-Host "  服务状态: $status" -ForegroundColor $(if ($status -like "*RUNNING*") { "Green" } else { "Yellow" })

# 检查端口
$portCheck = netstat -ano | Select-String ":5000.*LISTENING"
if ($portCheck) {
    Write-Host "  ✓ 端口 5000 正在监听" -ForegroundColor Green
} else {
    Write-Host "  ⚠ 端口 5000 未监听" -ForegroundColor Yellow
}

# 显示最新日志
Write-Host ""
Write-Host "最新错误日志 (最后 5 行):" -ForegroundColor Cyan
$errorLog = Join-Path $PSScriptRoot "logs\nssm_error.log"
if (Test-Path $errorLog) {
    Get-Content $errorLog -Tail 5 -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }
} else {
    Write-Host "  未找到错误日志文件" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

# NSSM 服务自动安装脚本
# 使用方法：以管理员身份运行 PowerShell，然后执行：.\install_nssm_service.ps1

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "错误：此脚本需要管理员权限！" -ForegroundColor Red
    Write-Host "请以管理员身份运行 PowerShell，然后重新执行此脚本。" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TR Backend NSSM 服务安装脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 配置变量
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = $scriptDir
$nssmDir = Join-Path $backendDir "nssm-2.24"
$nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
$nssmZip = Join-Path $backendDir "nssm-2.24.zip"
$serviceName = "TR-Backend"
$logDir = Join-Path $backendDir "logs"

# 步骤 1：检测 Python 路径
Write-Host "[1/8] 检测 Python 路径..." -ForegroundColor Yellow
try {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    Write-Host "找到 Python: $pythonPath" -ForegroundColor Green
} catch {
    Write-Host "错误：未找到 Python！请确保 Python 已安装并在 PATH 中。" -ForegroundColor Red
    pause
    exit 1
}

# 验证 Python 版本
$pythonVersion = python --version 2>&1
Write-Host "Python 版本: $pythonVersion" -ForegroundColor Green
Write-Host ""

# 步骤 2：检查工作目录
Write-Host "[2/8] 检查工作目录..." -ForegroundColor Yellow
if (-not (Test-Path $backendDir)) {
    Write-Host "错误：后端目录不存在: $backendDir" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "工作目录: $backendDir" -ForegroundColor Green

# 检查启动脚本
$startScript = Join-Path $backendDir "start_waitress.py"
if (-not (Test-Path $startScript)) {
    Write-Host "错误：启动脚本不存在: $startScript" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "启动脚本: $startScript" -ForegroundColor Green
Write-Host ""

# 步骤 3：创建日志目录
Write-Host "[3/8] 创建日志目录..." -ForegroundColor Yellow
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Write-Host "已创建日志目录: $logDir" -ForegroundColor Green
} else {
    Write-Host "日志目录已存在: $logDir" -ForegroundColor Green
}
Write-Host ""

# 步骤 4：下载 NSSM
Write-Host "[4/8] 下载 NSSM..." -ForegroundColor Yellow
if (-not (Test-Path $nssmDir)) {
    New-Item -ItemType Directory -Force -Path $nssmDir | Out-Null
}

# 检测系统架构
$arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
$nssmExe = Join-Path $nssmDir $arch "nssm.exe"

if (-not (Test-Path $nssmExe)) {
    Write-Host "正在下载 NSSM..." -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip -UseBasicParsing
        Write-Host "下载完成，正在解压..." -ForegroundColor Yellow
        Expand-Archive -Path $nssmZip -DestinationPath $nssmDir -Force
        Remove-Item $nssmZip -Force
        Write-Host "NSSM 已下载并解压" -ForegroundColor Green
    } catch {
        Write-Host "错误：下载 NSSM 失败: $_" -ForegroundColor Red
        Write-Host "请手动下载: $nssmUrl" -ForegroundColor Yellow
        pause
        exit 1
    }
} else {
    Write-Host "NSSM 已存在: $nssmExe" -ForegroundColor Green
}
Write-Host ""

# 步骤 5：检查服务是否已存在
Write-Host "[5/8] 检查现有服务..." -ForegroundColor Yellow
$existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "警告：服务 '$serviceName' 已存在！" -ForegroundColor Yellow
    $response = Read-Host "是否要删除现有服务并重新安装? (Y/N)"
    if ($response -eq 'Y' -or $response -eq 'y') {
        Write-Host "正在停止并删除现有服务..." -ForegroundColor Yellow
        if ($existingService.Status -eq 'Running') {
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        & $nssmExe remove $serviceName confirm
        Start-Sleep -Seconds 1
        Write-Host "现有服务已删除" -ForegroundColor Green
    } else {
        Write-Host "已取消安装" -ForegroundColor Yellow
        pause
        exit 0
    }
}
Write-Host ""

# 步骤 6：安装服务
Write-Host "[6/8] 安装 NSSM 服务..." -ForegroundColor Yellow
try {
    # 安装服务
    & $nssmExe install $serviceName $pythonPath "start_waitress.py"
    
    # 设置工作目录
    & $nssmExe set $serviceName AppDirectory $backendDir
    
    # 设置服务详情
    & $nssmExe set $serviceName DisplayName "TR Report System Backend"
    & $nssmExe set $serviceName Description "TR Report System Backend API Server"
    & $nssmExe set $serviceName Start SERVICE_AUTO_START
    
    # 设置日志
    & $nssmExe set $serviceName AppStdout (Join-Path $logDir "nssm_output.log")
    & $nssmExe set $serviceName AppStderr (Join-Path $logDir "nssm_error.log")
    & $nssmExe set $serviceName AppRotateFiles 1
    & $nssmExe set $serviceName AppRotateOnline 1
    & $nssmExe set $serviceName AppRotateSeconds 86400
    & $nssmExe set $serviceName AppRotateBytes 10485760
    
    # 设置环境变量
    & $nssmExe set $serviceName AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8"
    
    # 设置退出行为（自动重启）
    & $nssmExe set $serviceName AppExit Default Restart
    & $nssmExe set $serviceName AppRestartDelay 5000
    
    # 设置进程优先级
    & $nssmExe set $serviceName AppPriority NORMAL_PRIORITY_CLASS
    
    Write-Host "服务安装成功！" -ForegroundColor Green
} catch {
    Write-Host "错误：安装服务失败: $_" -ForegroundColor Red
    pause
    exit 1
}
Write-Host ""

# 步骤 7：启动服务
Write-Host "[7/8] 启动服务..." -ForegroundColor Yellow
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
    Write-Host "请检查错误日志: $(Join-Path $logDir 'nssm_error.log')" -ForegroundColor Yellow
}
Write-Host ""

# 步骤 8：验证服务
Write-Host "[8/8] 验证服务..." -ForegroundColor Yellow
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "服务名称: $($service.Name)" -ForegroundColor Green
    Write-Host "显示名称: $($service.DisplayName)" -ForegroundColor Green
    Write-Host "状态: $($service.Status)" -ForegroundColor Green
    Write-Host "启动类型: $($service.StartType)" -ForegroundColor Green
} else {
    Write-Host "警告：无法获取服务信息" -ForegroundColor Yellow
}

# 检查端口
Write-Host ""
Write-Host "检查端口 5000..." -ForegroundColor Yellow
$portCheck = netstat -ano | Select-String ":5000" | Select-String "LISTENING"
if ($portCheck) {
    Write-Host "端口 5000 正在监听" -ForegroundColor Green
} else {
    Write-Host "警告：端口 5000 未监听，服务可能未正常启动" -ForegroundColor Yellow
    Write-Host "请查看错误日志: $(Join-Path $logDir 'nssm_error.log')" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "服务管理命令：" -ForegroundColor Cyan
Write-Host "  启动:   Start-Service TR-Backend" -ForegroundColor White
Write-Host "  停止:   Stop-Service TR-Backend" -ForegroundColor White
Write-Host "  重启:   Restart-Service TR-Backend" -ForegroundColor White
Write-Host "  状态:   Get-Service TR-Backend" -ForegroundColor White
Write-Host ""
Write-Host "查看日志：" -ForegroundColor Cyan
Write-Host "  输出日志: Get-Content '$logDir\nssm_output.log' -Tail 50" -ForegroundColor White
Write-Host "  错误日志: Get-Content '$logDir\nssm_error.log' -Tail 50" -ForegroundColor White
Write-Host ""
Write-Host "详细文档: NSSM_SETUP_GUIDE.md" -ForegroundColor Cyan
Write-Host ""

pause

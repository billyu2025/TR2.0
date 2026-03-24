# ============================================
# 配置 NSSM 服务使用 PostgreSQL 数据库
# ============================================
# 功能：为 NSSM 运行的 TR-Backend 服务配置 PostgreSQL 环境变量
# 使用方法：以管理员身份运行此脚本
# ============================================

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "错误：此脚本需要管理员权限！" -ForegroundColor Red
    Write-Host "请右键点击 PowerShell，选择'以管理员身份运行'" -ForegroundColor Yellow
    pause
    exit 1
}

# 配置参数
$serviceName = "TR-Backend"
$backendDir = "C:\TR-master\TR UI\backend"
$nssmExe = Join-Path $backendDir "nssm-2.24\win64\nssm.exe"

# PostgreSQL 连接配置（根据实际情况修改）
$postgresDsn = "postgresql://postgres:postgres@127.0.0.1:5432/tr_db"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "配置 NSSM 服务使用 PostgreSQL" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 检查 NSSM 是否存在
if (-not (Test-Path $nssmExe)) {
    Write-Host "错误：找不到 NSSM 可执行文件: $nssmExe" -ForegroundColor Red
    Write-Host "请确保 NSSM 已解压到正确位置" -ForegroundColor Yellow
    pause
    exit 1
}

# 检查服务是否存在
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "错误：服务 $serviceName 不存在！" -ForegroundColor Red
    Write-Host "请先安装 NSSM 服务" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "[1/5] 检查服务状态..." -ForegroundColor Yellow
$serviceStatus = $service.Status
Write-Host "  当前服务状态: $serviceStatus" -ForegroundColor Gray

# 如果服务正在运行，先停止
if ($serviceStatus -eq 'Running') {
    Write-Host "[2/5] 停止服务..." -ForegroundColor Yellow
    try {
        Stop-Service -Name $serviceName -Force
        Start-Sleep -Seconds 3
        Write-Host "  ✅ 服务已停止" -ForegroundColor Green
    } catch {
        Write-Host "  ⚠️  警告：停止服务时出错: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/5] 服务未运行，跳过停止步骤" -ForegroundColor Gray
}

# 获取当前环境变量
Write-Host "[3/5] 读取当前环境变量..." -ForegroundColor Yellow
try {
    $currentEnv = & $nssmExe get $serviceName AppEnvironmentExtra 2>$null
    Write-Host "  当前环境变量已读取" -ForegroundColor Gray
} catch {
    Write-Host "  当前没有设置环境变量" -ForegroundColor Gray
    $currentEnv = ""
}

# 构建新的环境变量列表
Write-Host "[4/5] 配置 PostgreSQL 环境变量..." -ForegroundColor Yellow
try {
    $newEnvVars = @()
    
    # 保留现有的非数据库相关环境变量
    if ($currentEnv) {
        $lines = $currentEnv -split "`n" | Where-Object {
            $line = $_
            if (-not $line) { return $false }
            if ($line -match "^\s*$") { return $false }
            if ($line -match "^(DB_BACKEND|POSTGRES_DSN|SQLITE_DB_PATH)=") { return $false }
            return $true
        }
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if ($trimmed) {
                $newEnvVars += $trimmed
            }
        }
    }
    
    # 添加默认环境变量（如果不存在）
    $defaultVars = @(
        "API_HOST=0.0.0.0",
        "API_PORT=5000",
        "DEBUG=False",
        "WAITRESS_THREADS=8"
    )
    
    foreach ($var in $defaultVars) {
        $varName = $var -split "=" | Select-Object -First 1
        $exists = $newEnvVars | Where-Object { $_ -match "^$varName=" }
        if (-not $exists) {
            $newEnvVars += $var
        }
    }
    
    # 添加 PostgreSQL 环境变量（优先级最高，会覆盖之前的设置）
    $newEnvVars = $newEnvVars | Where-Object { $_ -notmatch "^(DB_BACKEND|POSTGRES_DSN)=" }
    $newEnvVars += "DB_BACKEND=postgres"
    $newEnvVars += "POSTGRES_DSN=$postgresDsn"
    
    # 设置环境变量
    & $nssmExe set $serviceName AppEnvironmentExtra $newEnvVars
    
    Write-Host "  ✅ 环境变量已配置：" -ForegroundColor Green
    Write-Host "     DB_BACKEND=postgres" -ForegroundColor Gray
    Write-Host "     POSTGRES_DSN=$postgresDsn" -ForegroundColor Gray
    
    # 显示所有环境变量
    Write-Host ""
    Write-Host "  完整环境变量列表：" -ForegroundColor Cyan
    foreach ($var in $newEnvVars) {
        Write-Host "    - $var" -ForegroundColor DarkGray
    }
    
} catch {
    Write-Host "  ❌ 错误：配置环境变量失败: $_" -ForegroundColor Red
    pause
    exit 1
}

# 启动服务
Write-Host "[5/5] 启动服务..." -ForegroundColor Yellow
try {
    Start-Service -Name $serviceName
    Start-Sleep -Seconds 3
    
    $service = Get-Service -Name $serviceName
    if ($service.Status -eq 'Running') {
        Write-Host "  ✅ 服务启动成功！" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  服务状态: $($service.Status)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ❌ 错误：启动服务失败: $_" -ForegroundColor Red
    Write-Host "  请检查日志文件: $backendDir\logs\nssm_error.log" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "配置完成！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "验证步骤：" -ForegroundColor Yellow
Write-Host "1. 查看日志确认使用 PostgreSQL：" -ForegroundColor Gray
Write-Host "   Get-Content `"$backendDir\logs\app.log`" -Tail 20" -ForegroundColor DarkGray
Write-Host ""
Write-Host "2. 测试 API 连接：" -ForegroundColor Gray
Write-Host "   在浏览器中访问: http://localhost:5000/health" -ForegroundColor DarkGray
Write-Host ""
Write-Host "3. 检查服务状态：" -ForegroundColor Gray
Write-Host "   Get-Service TR-Backend" -ForegroundColor DarkGray
Write-Host ""
Write-Host "4. 查看当前环境变量：" -ForegroundColor Gray
Write-Host "   & `"$nssmExe`" get TR-Backend AppEnvironmentExtra" -ForegroundColor DarkGray
Write-Host ""

pause

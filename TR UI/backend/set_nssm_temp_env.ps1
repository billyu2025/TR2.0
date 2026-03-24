# 设置 NSSM 服务的临时目录环境变量
# 需要以管理员身份运行

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "设置 NSSM 服务临时目录环境变量" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "错误: 需要管理员权限来修改 NSSM 服务配置" -ForegroundColor Red
    Write-Host "请以管理员身份运行 PowerShell，然后重新执行此脚本" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "或者，您可以手动运行以下命令:" -ForegroundColor Yellow
    Write-Host "cd `"C:\TR-master\TR UI\backend`"" -ForegroundColor Gray
    Write-Host '& ".\nssm-2.24\win64\nssm.exe" set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8" "DB_BACKEND=postgres" "POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db" "TEMP=C:\Users\tradmin\AppData\Local\Temp\1" "TMP=C:\Users\tradmin\AppData\Local\Temp\1"' -ForegroundColor Gray
    exit 1
}

# 设置变量
$nssmExe = ".\nssm-2.24\win64\nssm.exe"
$serviceName = "TR-Backend"
$tempDir = "C:\Users\tradmin\AppData\Local\Temp\1"

# 检查 NSSM 是否存在
if (-not (Test-Path $nssmExe)) {
    Write-Host "错误: 找不到 NSSM 可执行文件: $nssmExe" -ForegroundColor Red
    exit 1
}

Write-Host "当前工作目录: $(Get-Location)" -ForegroundColor Gray
Write-Host "NSSM 路径: $nssmExe" -ForegroundColor Gray
Write-Host "服务名称: $serviceName" -ForegroundColor Gray
Write-Host "临时目录: $tempDir" -ForegroundColor Gray
Write-Host ""

# 检查服务是否存在
Write-Host "检查服务状态..." -ForegroundColor Yellow
$serviceStatus = & $nssmExe status $serviceName 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 服务 $serviceName 不存在或无法访问" -ForegroundColor Red
    exit 1
}
Write-Host "服务状态: $serviceStatus" -ForegroundColor Green
Write-Host ""

# 获取当前环境变量
Write-Host "获取当前环境变量配置..." -ForegroundColor Yellow
$currentEnv = & $nssmExe get $serviceName AppEnvironmentExtra 2>&1
Write-Host "当前配置:" -ForegroundColor Cyan
Write-Host $currentEnv
Write-Host ""

# 设置新的环境变量（包括所有现有变量和新的 TEMP/TMP）
Write-Host "设置新的环境变量（包括 TEMP 和 TMP）..." -ForegroundColor Yellow
$envVars = @(
    "API_HOST=0.0.0.0",
    "API_PORT=5000",
    "DEBUG=False",
    "WAITRESS_THREADS=8",
    "DB_BACKEND=postgres",
    "POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db",
    "TEMP=$tempDir",
    "TMP=$tempDir"
)

$result = & $nssmExe set $serviceName AppEnvironmentExtra $envVars 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "环境变量设置成功!" -ForegroundColor Green
} else {
    Write-Host "错误: 设置环境变量失败" -ForegroundColor Red
    Write-Host $result
    exit 1
}
Write-Host ""

# 验证设置
Write-Host "验证新的环境变量配置..." -ForegroundColor Yellow
$newEnv = & $nssmExe get $serviceName AppEnvironmentExtra 2>&1
Write-Host "新配置:" -ForegroundColor Cyan
Write-Host $newEnv
Write-Host ""

# 检查是否包含 TEMP 和 TMP
if ($newEnv -match "TEMP=" -and $newEnv -match "TMP=") {
    Write-Host "✓ TEMP 和 TMP 环境变量已成功设置" -ForegroundColor Green
} else {
    Write-Host "警告: TEMP 或 TMP 环境变量可能未正确设置" -ForegroundColor Yellow
}
Write-Host ""

# 询问是否重启服务
Write-Host "需要重启服务以使新的环境变量生效" -ForegroundColor Yellow
$restart = Read-Host "是否现在重启服务? (Y/N)"
if ($restart -eq "Y" -or $restart -eq "y") {
    Write-Host "正在重启服务..." -ForegroundColor Yellow
    & $nssmExe restart $serviceName 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "服务重启成功!" -ForegroundColor Green
        Start-Sleep -Seconds 3
        $finalStatus = & $nssmExe status $serviceName 2>&1
        Write-Host "服务最终状态: $finalStatus" -ForegroundColor Cyan
    } else {
        Write-Host "警告: 服务重启可能失败，请手动检查" -ForegroundColor Yellow
    }
} else {
    Write-Host "跳过服务重启。请稍后手动重启服务以应用新配置" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "配置完成!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan

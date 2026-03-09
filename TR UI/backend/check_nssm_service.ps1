# NSSM 服务诊断脚本
# 使用方法：以管理员身份运行 PowerShell，然后执行：.\check_nssm_service.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NSSM 服务诊断" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

cd "C:\TR-master\TR UI\backend"

# 1. 检查服务是否存在
Write-Host "[1/5] 检查服务状态..." -ForegroundColor Yellow
$service = Get-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "✅ 服务存在" -ForegroundColor Green
    Write-Host "   服务名称: $($service.Name)" -ForegroundColor White
    Write-Host "   显示名称: $($service.DisplayName)" -ForegroundColor White
    Write-Host "   状态: $($service.Status)" -ForegroundColor $(if ($service.Status -eq 'Running') { 'Green' } else { 'Yellow' })
    Write-Host "   启动类型: $($service.StartType)" -ForegroundColor White
} else {
    Write-Host "❌ 服务不存在" -ForegroundColor Red
    Write-Host "   需要先安装服务，运行: .\install_nssm_service.ps1" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

Write-Host ""

# 2. 检查端口监听
Write-Host "[2/5] 检查端口 5000..." -ForegroundColor Yellow
$port = netstat -ano | Select-String ":5000" | Select-String "LISTENING"
if ($port) {
    Write-Host "✅ 端口 5000 正在监听" -ForegroundColor Green
    Write-Host "   $port" -ForegroundColor White
} else {
    Write-Host "❌ 端口 5000 未监听" -ForegroundColor Red
    if ($service.Status -ne 'Running') {
        Write-Host "   服务未运行，需要启动服务" -ForegroundColor Yellow
    } else {
        Write-Host "   服务在运行但端口未监听，可能启动失败" -ForegroundColor Yellow
    }
}

Write-Host ""

# 3. 检查 NSSM 配置
Write-Host "[3/5] 检查 NSSM 配置..." -ForegroundColor Yellow
$nssm = "nssm-2.24\win64\nssm.exe"
if (Test-Path $nssm) {
    Write-Host "✅ NSSM 存在" -ForegroundColor Green
    
    try {
        $pythonPath = & $nssm get TR-Backend Application 2>$null
        $workDir = & $nssm get TR-Backend AppDirectory 2>$null
        $params = & $nssm get TR-Backend AppParameters 2>$null
        
        if ($pythonPath) {
            Write-Host "   Python 路径: $pythonPath" -ForegroundColor White
            if (Test-Path $pythonPath) {
                Write-Host "   ✅ Python 路径有效" -ForegroundColor Green
            } else {
                Write-Host "   ❌ Python 路径无效: $pythonPath" -ForegroundColor Red
            }
        }
        
        if ($workDir) {
            Write-Host "   工作目录: $workDir" -ForegroundColor White
            if (Test-Path $workDir) {
                Write-Host "   ✅ 工作目录有效" -ForegroundColor Green
            } else {
                Write-Host "   ❌ 工作目录无效: $workDir" -ForegroundColor Red
            }
        }
        
        if ($params) {
            Write-Host "   启动参数: $params" -ForegroundColor White
        }
    } catch {
        Write-Host "   ⚠️ 无法读取配置: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ NSSM 不存在: $nssm" -ForegroundColor Red
}

Write-Host ""

# 4. 检查错误日志
Write-Host "[4/5] 检查错误日志..." -ForegroundColor Yellow
$errorLog = "logs\nssm_error.log"
if (Test-Path $errorLog) {
    $errorContent = Get-Content $errorLog -Tail 10 -ErrorAction SilentlyContinue
    if ($errorContent) {
        Write-Host "⚠️ 最近的错误日志：" -ForegroundColor Yellow
        $errorContent | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
    } else {
        Write-Host "✅ 错误日志为空" -ForegroundColor Green
    }
} else {
    Write-Host "ℹ️ 错误日志文件不存在" -ForegroundColor Cyan
}

Write-Host ""

# 5. 检查输出日志
Write-Host "[5/5] 检查输出日志..." -ForegroundColor Yellow
$outputLog = "logs\nssm_output.log"
if (Test-Path $outputLog) {
    $outputContent = Get-Content $outputLog -Tail 10 -ErrorAction SilentlyContinue
    if ($outputContent) {
        Write-Host "ℹ️ 最近的输出日志：" -ForegroundColor Cyan
        $outputContent | ForEach-Object { Write-Host "   $_" -ForegroundColor White }
    } else {
        Write-Host "ℹ️ 输出日志为空" -ForegroundColor Cyan
    }
} else {
    Write-Host "ℹ️ 输出日志文件不存在" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "诊断完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 提供建议
if ($service.Status -ne 'Running') {
    Write-Host "建议操作：" -ForegroundColor Yellow
    Write-Host "  启动服务: Start-Service TR-Backend" -ForegroundColor White
} elseif (-not $port) {
    Write-Host "建议操作：" -ForegroundColor Yellow
    Write-Host "  1. 查看错误日志: Get-Content logs\nssm_error.log -Tail 50" -ForegroundColor White
    Write-Host "  2. 手动测试: python start_waitress.py" -ForegroundColor White
    Write-Host "  3. 重启服务: Restart-Service TR-Backend" -ForegroundColor White
} else {
    Write-Host "✅ 服务运行正常！" -ForegroundColor Green
}

Write-Host ""
pause

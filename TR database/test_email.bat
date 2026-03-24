@echo off
REM ============================================
REM Test Email Sending Script
REM ============================================

REM Enable error handling
setlocal enabledelayedexpansion

REM Set working directory to script directory
cd /d "%~dp0"
if errorlevel 1 (
    echo [ERROR] Cannot change to script directory: %~dp0
    pause
    exit /b 1
)

REM Set paths - send_email.ps1 is in TR UI\backend directory
set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%..\TR UI\backend"
REM Convert to absolute path
cd /d "%BACKEND_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot change to backend directory: %BACKEND_DIR%
    echo [ERROR] Please check if the path exists
    pause
    exit /b 1
)
set "BACKEND_DIR=%CD%"
cd /d "%SCRIPT_DIR%"

REM Email configuration (same as update_tr_tables_postgres.bat)
set SMTP_SERVER=corpmail1.netvigator.com
set SMTP_PORT=25
set EMAIL_FROM=tr@hkshalliance.com
set EMAIL_TO=henry.yu@hkshalliance.com,yuyuhang1991@163.com
set USE_SSL=false

echo ============================================
echo Testing Email Configuration
echo ============================================
echo.
echo [CONFIG] SMTP Server: %SMTP_SERVER%:%SMTP_PORT%
echo [CONFIG] From: %EMAIL_FROM%
echo [CONFIG] To: %EMAIL_TO%
echo [CONFIG] Use SSL: %USE_SSL%
echo [CONFIG] PowerShell Script: %BACKEND_DIR%\send_email.ps1
echo.

REM Check if PowerShell script exists
if not exist "%BACKEND_DIR%\send_email.ps1" (
    echo [ERROR] send_email.ps1 not found at: %BACKEND_DIR%\send_email.ps1
    echo.
    echo Please check if the file exists at the above path.
    echo.
    pause
    exit /b 1
)

echo [INFO] PowerShell script found
echo.

REM Convert backslash to forward slash for PowerShell path
set "PS_BACKEND_DIR=%BACKEND_DIR:\=/%"

REM Test email sending
echo [TEST] Sending test email...
echo.

REM Test email sending - call PowerShell script directly
echo [INFO] Preparing to send test email...
echo.

echo [INFO] Executing PowerShell script...
REM Call send_email.ps1 directly with parameters
powershell -ExecutionPolicy Bypass -NoProfile -Command "$ErrorActionPreference = 'Stop'; try { $Subject = 'TR Database Update Test Email'; $Body = 'This is a test email from TR Database update script.`n`nIf you receive this email, the email configuration is working correctly.'; $ToEmails = '%EMAIL_TO%' -split ',' | ForEach-Object { $_.Trim() }; Write-Host 'Email To:' ($ToEmails -join ', ') -ForegroundColor Gray; Write-Host 'Email From: %EMAIL_FROM%' -ForegroundColor Gray; Write-Host 'SMTP Server: %SMTP_SERVER%:%SMTP_PORT%' -ForegroundColor Gray; Write-Host 'Calling send_email.ps1...' -ForegroundColor Gray; & '%PS_BACKEND_DIR%/send_email.ps1' -Subject $Subject -Body $Body -To $ToEmails -SmtpServer '%SMTP_SERVER%' -SmtpPort %SMTP_PORT% -From '%EMAIL_FROM%' -UseSSL '%USE_SSL%'; $exitCode = $LASTEXITCODE; if ($exitCode -eq 0) { Write-Host 'Email sent successfully!' -ForegroundColor Green; exit 0 } else { Write-Host 'Email sending failed with exit code:' $exitCode -ForegroundColor Red; exit $exitCode } } catch { Write-Host 'PowerShell Error:' $_ -ForegroundColor Red; Write-Host 'Error Details:' $_.Exception.Message -ForegroundColor Red; exit 1 }"
set "TEST_EXIT_CODE=%errorlevel%"

REM If PowerShell execution failed, show error
if %TEST_EXIT_CODE% neq 0 (
    echo.
    echo [ERROR] PowerShell script execution failed
    echo [ERROR] Exit code: %TEST_EXIT_CODE%
    echo.
    echo Please check:
    echo   1. PowerShell is installed and accessible
    echo   2. send_email.ps1 exists at: %BACKEND_DIR%\send_email.ps1
    echo   3. Email configuration is correct
    echo   4. SMTP server is accessible
    echo.
)

echo.
echo ============================================
if %TEST_EXIT_CODE% equ 0 (
    echo Test Result: SUCCESS
    echo Please check your email inbox for the test email.
) else (
    echo Test Result: FAILED
    echo Exit Code: %TEST_EXIT_CODE%
    echo.
    echo Please check:
    echo   1. SMTP server is accessible
    echo   2. Email addresses are correct
    echo   3. Firewall is not blocking port %SMTP_PORT%
    echo   4. PowerShell execution policy allows script execution
)
echo ============================================
echo.
pause

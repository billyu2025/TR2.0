# TR 系统日志查看脚本
# 使用方法：.\view_logs.ps1 -Type [error|output|app] -Lines [number]

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("error", "output", "app", "all")]
    [string]$Type = "error",
    [Parameter(Mandatory=$false)]
    [int]$Lines = 50,
    [Parameter(Mandatory=$false)]
    [switch]$Follow = $false
)

$logDir = "C:\TR-master\TR UI\backend\logs"

function Show-Log {
    param(
        [string]$LogFile,
        [string]$Title,
        [string]$Color = "White"
    )
    
    if (Test-Path $LogFile) {
        Write-Host "`n=== $Title ===" -ForegroundColor $Color
        Write-Host "File: $LogFile" -ForegroundColor Gray
        Write-Host ("=" * 60) -ForegroundColor $Color
        
        if ($Follow) {
            Get-Content $LogFile -Wait -Tail $Lines
        } else {
            Get-Content $LogFile -Tail $Lines
        }
    } else {
        Write-Host "Log file not found: $LogFile" -ForegroundColor Red
    }
}

switch ($Type.ToLower()) {
    "error" {
        Show-Log -LogFile (Join-Path $logDir "nssm_error.log") -Title "NSSM Error Log (Last $Lines lines)" -Color "Red"
    }
    "output" {
        Show-Log -LogFile (Join-Path $logDir "nssm_output.log") -Title "NSSM Output Log (Last $Lines lines)" -Color "Cyan"
    }
    "app" {
        Show-Log -LogFile (Join-Path $logDir "app.log") -Title "Application Log (Last $Lines lines)" -Color "Yellow"
    }
    "all" {
        Show-Log -LogFile (Join-Path $logDir "nssm_error.log") -Title "NSSM Error Log (Last $Lines lines)" -Color "Red"
        Show-Log -LogFile (Join-Path $logDir "nssm_output.log") -Title "NSSM Output Log (Last $Lines lines)" -Color "Cyan"
        Show-Log -LogFile (Join-Path $logDir "app.log") -Title "Application Log (Last $Lines lines)" -Color "Yellow"
    }
}

if ($Follow) {
    Write-Host "`nPress Ctrl+C to stop monitoring..." -ForegroundColor Yellow
}

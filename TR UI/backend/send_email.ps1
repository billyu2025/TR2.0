# PowerShell Email Sending Script
# Usage: .\send_email.ps1 -Subject "Subject" -Body "Content" -To "recipient@example.com"

param(
    [Parameter(Mandatory=$true)]
    [string]$Subject,
    
    [Parameter(Mandatory=$true)]
    [string]$Body,
    
    [Parameter(Mandatory=$false)]
    [string[]]$To = @(),
    
    [Parameter(Mandatory=$false)]
    [string[]]$Cc = @(),
    
    [Parameter(Mandatory=$false)]
    [string]$SmtpServer = $env:SMTP_SERVER,
    
    [Parameter(Mandatory=$false)]
    [int]$SmtpPort = 25,
    
    [Parameter(Mandatory=$false)]
    [string]$From = $env:EMAIL_FROM,
    
    [Parameter(Mandatory=$false)]
    [string]$Username = $env:SMTP_USERNAME,
    
    [Parameter(Mandatory=$false)]
    [string]$Password = $env:SMTP_PASSWORD,
    
    [Parameter(Mandatory=$false)]
    [string]$UseSSL = "false",
    
    [Parameter(Mandatory=$false)]
    [string[]]$Attachments = @()
)

# 如果没有配置收件人，尝试从环境变量读取
if ($To.Count -eq 0) {
    $envTo = $env:EMAIL_TO
    if ($envTo) {
        $To = $envTo -split ','
    } else {
        Write-Host "Error: Recipient not specified, please set EMAIL_TO environment variable or use -To parameter" -ForegroundColor Red
        exit 1
    }
}

# 如果没有配置发件人，尝试从环境变量读取
if (-not $From) {
    $From = $env:EMAIL_FROM
    if (-not $From -or $From -eq '') {
        Write-Host "Info: Sender not specified, skipping email notification" -ForegroundColor Yellow
        exit 0
    }
}

# 如果没有配置 SMTP 服务器，尝试从环境变量读取
if (-not $SmtpServer) {
    $SmtpServer = $env:SMTP_SERVER
    if (-not $SmtpServer) {
        Write-Host "Error: SMTP server not specified, please set SMTP_SERVER environment variable or use -SmtpServer parameter" -ForegroundColor Red
        exit 1
    }
}

try {
    # 创建邮件消息
    $mailParams = @{
        From = $From
        To = $To
        Subject = $Subject
        Body = $Body
        SmtpServer = $SmtpServer
        Port = $SmtpPort
        Encoding = [System.Text.Encoding]::UTF8
    }
    
    # 添加可选参数
    if ($Cc.Count -gt 0) {
        $mailParams['Cc'] = $Cc
    }
    
    if ($Attachments.Count -gt 0) {
        $mailParams['Attachments'] = $Attachments
    }
    
    if ($UseSSL -eq "true" -or $UseSSL -eq $true) {
        $mailParams['UseSsl'] = $true
    }
    
    # 如果提供了用户名和密码，使用凭据
    # 如果密码为空，尝试匿名发送（某些内部 SMTP 服务器支持）
    if ($Username -and $Username -ne '') {
        if ($Password -and $Password -ne '') {
            $securePassword = ConvertTo-SecureString $Password -AsPlainText -Force
            $credential = New-Object System.Management.Automation.PSCredential($Username, $securePassword)
            $mailParams['Credential'] = $credential
        } else {
            # 密码为空，尝试匿名发送
            Write-Host "Info: Password is empty, attempting anonymous send..." -ForegroundColor Yellow
        }
    }
    
    # 发送邮件
    Send-MailMessage @mailParams
    
    Write-Host "Email sent successfully!" -ForegroundColor Green
    Write-Host "  From: $From" -ForegroundColor Gray
    Write-Host "  To: $($To -join ', ')" -ForegroundColor Gray
    Write-Host "  Subject: $Subject" -ForegroundColor Gray
    exit 0
} catch {
    Write-Host "Email sending failed: $_" -ForegroundColor Red
    exit 1
}

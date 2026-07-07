@echo off
REM Launcher without spaces in path — for Windows Task Scheduler
call "C:\TR-master\TR UI\backend\daily_download_report.bat"
exit /b %ERRORLEVEL%

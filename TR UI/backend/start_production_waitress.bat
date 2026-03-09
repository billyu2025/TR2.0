@echo off
REM TR Report System 生產環境啟動腳本 (Windows - 使用 Waitress)

REM 設置環境變量
set API_HOST=0.0.0.0
set API_PORT=5000
set DEBUG=False

REM 創建日誌目錄
if not exist logs mkdir logs

REM 檢查 Waitress 是否安裝
python -c "import waitress" 2>nul
if errorlevel 1 (
    echo 錯誤: Waitress 未安裝
    echo 請運行: pip install waitress
    pause
    exit /b 1
)

REM 啟動 Waitress
echo 正在啟動 TR Report System (生產模式 - Waitress)...
echo 服務器地址: http://%API_HOST%:%API_PORT%
echo 按 Ctrl+C 停止服務器
echo.

python start_waitress.py

pause

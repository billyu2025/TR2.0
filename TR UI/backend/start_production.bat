@echo off
REM TR Report System 生產環境啟動腳本 (Windows)

REM 設置環境變量
set API_HOST=0.0.0.0
set API_PORT=5000
set DEBUG=False

REM 創建日誌目錄
if not exist logs mkdir logs

REM 檢查 Gunicorn 是否安裝
python -c "import gunicorn" 2>nul
if errorlevel 1 (
    echo 錯誤: Gunicorn 未安裝
    echo 請運行: pip install gunicorn
    pause
    exit /b 1
)

REM 啟動 Gunicorn
echo 正在啟動 TR Report System (生產模式)...
gunicorn -c gunicorn_config.py tr_fill_in_api:app

pause

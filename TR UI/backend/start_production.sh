#!/bin/bash
# TR Report System 生產環境啟動腳本

# 設置環境變量
export API_HOST=0.0.0.0
export API_PORT=5000
export DEBUG=False

# 創建日誌目錄
mkdir -p logs

# 檢查 Gunicorn 是否安裝
if ! command -v gunicorn &> /dev/null; then
    echo "錯誤: Gunicorn 未安裝"
    echo "請運行: pip install gunicorn"
    exit 1
fi

# 啟動 Gunicorn
echo "正在啟動 TR Report System (生產模式)..."
gunicorn -c gunicorn_config.py tr_fill_in_api:app

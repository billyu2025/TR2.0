#!/bin/bash
# TR Report System - WSL 快速部署脚本
# 使用方法: bash wsl_deploy.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "TR Report System - WSL 部署脚本"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 获取当前用户名
USERNAME=$(whoami)
HOME_DIR="/home/$USERNAME"
PROJECT_DIR="$HOME_DIR/tr-master"
BACKEND_DIR="$PROJECT_DIR/TR UI/backend"

# 步骤 1: 检查 WSL 环境
echo -e "\n${YELLOW}[步骤 1/10] 检查 WSL 环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: Python3 未安装${NC}"
    echo "正在安装 Python3..."
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv
fi

if ! command -v nginx &> /dev/null; then
    echo "正在安装 Nginx..."
    sudo apt install -y nginx
fi

echo -e "${GREEN}✓ WSL 环境检查完成${NC}"

# 步骤 2: 创建项目目录
echo -e "\n${YELLOW}[步骤 2/10] 创建项目目录...${NC}"
mkdir -p "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/stockist-test-report"
echo -e "${GREEN}✓ 项目目录创建完成${NC}"

# 步骤 3: 检查项目文件
echo -e "\n${YELLOW}[步骤 3/10] 检查项目文件...${NC}"
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${YELLOW}警告: 项目文件未找到${NC}"
    echo "请确保项目文件已复制到: $PROJECT_DIR"
    echo "或者从 Windows 复制:"
    echo "  cp -r /mnt/c/TR-master/TR\\ UI $PROJECT_DIR/"
    echo "  cp -r /mnt/c/TR-master/TR\\ database $PROJECT_DIR/"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ 项目文件已存在${NC}"
fi

# 步骤 4: 检查数据库文件
echo -e "\n${YELLOW}[步骤 4/10] 检查数据库文件...${NC}"
DB_PATH="$PROJECT_DIR/TR database/data_3years.db"
if [ ! -f "$DB_PATH" ]; then
    echo -e "${YELLOW}警告: 数据库文件未找到${NC}"
    echo "请确保数据库文件已复制到: $DB_PATH"
    echo "或者从 Windows 复制:"
    echo "  mkdir -p \"$PROJECT_DIR/TR database\""
    echo "  cp /mnt/c/TR-master/TR\\ database/data_3years.db \"$DB_PATH\""
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ 数据库文件已存在${NC}"
    # 设置数据库文件权限
    chmod 644 "$DB_PATH"
fi

# 步骤 5: 创建 Python 虚拟环境
echo -e "\n${YELLOW}[步骤 5/10] 创建 Python 虚拟环境...${NC}"
cd "$BACKEND_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ 虚拟环境创建完成${NC}"
else
    echo -e "${GREEN}✓ 虚拟环境已存在${NC}"
fi

# 步骤 6: 安装依赖
echo -e "\n${YELLOW}[步骤 6/10] 安装 Python 依赖...${NC}"
source venv/bin/activate

# 安装系统依赖（WeasyPrint 需要）
echo "安装系统依赖..."
sudo apt install -y \
    python3-dev \
    python3-cffi \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    build-essential \
    || echo -e "${YELLOW}警告: 部分系统依赖安装失败，但继续...${NC}"

# 升级 pip
pip install --upgrade pip

# 安装 Python 依赖
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Python 依赖安装完成${NC}"
else
    echo -e "${RED}错误: requirements.txt 未找到${NC}"
    exit 1
fi

# 步骤 7: 创建环境变量文件
echo -e "\n${YELLOW}[步骤 7/10] 配置环境变量...${NC}"
if [ ! -f ".env" ]; then
    cat > .env << EOF
# 数据库路径（WSL 路径）
DB_PATH=$DB_PATH

# Stockist&Test Report 文件夹路径（WSL 路径）
STOCKIST_TEST_FOLDER=$PROJECT_DIR/stockist-test-report

# 服务器配置
API_HOST=0.0.0.0
API_PORT=5000
DEBUG=False

# 会话配置
SESSION_TTL_HOURS=24
PASSWORD_ITERATIONS=120000

# Redis 配置（可选）
REDIS_ENABLED=False
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
EOF
    echo -e "${GREEN}✓ 环境变量文件创建完成${NC}"
else
    echo -e "${GREEN}✓ 环境变量文件已存在${NC}"
fi

# 步骤 8: 创建日志目录
echo -e "\n${YELLOW}[步骤 8/10] 创建日志目录...${NC}"
mkdir -p logs
chmod 755 logs
echo -e "${GREEN}✓ 日志目录创建完成${NC}"

# 步骤 9: 配置 Nginx
echo -e "\n${YELLOW}[步骤 9/10] 配置 Nginx...${NC}"
NGINX_CONFIG="/etc/nginx/sites-available/tr-report"
NGINX_ENABLED="/etc/nginx/sites-enabled/tr-report"

# 创建 Nginx 配置
sudo tee "$NGINX_CONFIG" > /dev/null << EOF
server {
    listen 80;
    server_name _;
    
    charset utf-8;
    
    location / {
        root $PROJECT_DIR/TR UI;
        index login.html;
        try_files \$uri \$uri/ /login.html;
    }
    
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        
        proxy_connect_timeout 1800s;
        proxy_send_timeout 1800s;
        proxy_read_timeout 1800s;
        
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
    }
    
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF

# 创建符号链接
if [ ! -L "$NGINX_ENABLED" ]; then
    sudo ln -s "$NGINX_CONFIG" "$NGINX_ENABLED"
fi

# 删除默认配置（可选）
if [ -L "/etc/nginx/sites-enabled/default" ]; then
    sudo rm /etc/nginx/sites-enabled/default
fi

# 测试 Nginx 配置
if sudo nginx -t; then
    echo -e "${GREEN}✓ Nginx 配置验证成功${NC}"
    sudo systemctl reload nginx || sudo systemctl restart nginx
    echo -e "${GREEN}✓ Nginx 已重载${NC}"
else
    echo -e "${RED}错误: Nginx 配置验证失败${NC}"
    exit 1
fi

# 步骤 10: 创建启动脚本
echo -e "\n${YELLOW}[步骤 10/10] 创建启动脚本...${NC}"
cat > start_gunicorn.sh << 'SCRIPT_EOF'
#!/bin/bash
# TR Report System Gunicorn 启动脚本

cd "$(dirname "$0")"

# 激活虚拟环境
source venv/bin/activate

# 设置环境变量
export API_HOST=0.0.0.0
export API_PORT=5000
export DEBUG=False

# 创建日志目录
mkdir -p logs

# 启动 Gunicorn
echo "正在启动 TR Report System (Gunicorn)..."
gunicorn -c gunicorn_config.py tr_fill_in_api:app
SCRIPT_EOF

chmod +x start_gunicorn.sh
echo -e "${GREEN}✓ 启动脚本创建完成${NC}"

# 完成
echo -e "\n${GREEN}=========================================="
echo "部署完成！"
echo "==========================================${NC}"

echo -e "\n${YELLOW}下一步操作:${NC}"
echo "1. 启动 Gunicorn:"
echo "   cd $BACKEND_DIR"
echo "   ./start_gunicorn.sh"
echo ""
echo "2. 或者使用 systemd 服务（推荐生产环境）:"
echo "   参考 WSL_DEPLOYMENT_GUIDE.md 中的 systemd 配置"
echo ""
echo "3. 测试服务:"
echo "   curl http://localhost:5000/health"
echo "   curl http://localhost/health"
echo ""
echo "4. 查看日志:"
echo "   tail -f $BACKEND_DIR/logs/gunicorn_access.log"
echo "   tail -f $BACKEND_DIR/logs/gunicorn_error.log"
echo ""
echo "5. 获取 WSL IP 地址:"
echo "   hostname -I"
echo "   然后在 Windows 浏览器中访问: http://WSL-IP/"
echo ""

# 询问是否立即启动
read -p "是否立即启动 Gunicorn? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "\n${YELLOW}启动 Gunicorn...${NC}"
    ./start_gunicorn.sh
fi

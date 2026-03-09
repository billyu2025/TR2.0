# TR Report System - WSL 部署完整指南

## 📋 目录

1. [环境准备](#环境准备)
2. [项目文件迁移](#项目文件迁移)
3. [Python 环境配置](#python-环境配置)
4. [数据库和文件路径配置](#数据库和文件路径配置)
5. [Gunicorn 配置](#gunicorn-配置)
6. [Nginx 配置](#nginx-配置)
7. [服务启动和管理](#服务启动和管理)
8. [测试验证](#测试验证)
9. [常见问题](#常见问题)

---

## 环境准备

### 步骤 1：安装 WSL2

如果还没有安装 WSL2：

```powershell
# 在 PowerShell (管理员权限) 中运行
wsl --install

# 或者指定发行版
wsl --install -d Ubuntu-22.04
```

### 步骤 2：验证 WSL 安装

```bash
# 在 WSL 中运行
wsl --version
uname -a
```

### 步骤 3：更新系统

```bash
# 进入 WSL
wsl

# 更新系统包
sudo apt update
sudo apt upgrade -y

# 安装基础工具
sudo apt install -y build-essential python3-pip python3-venv nginx git
```

---

## 项目文件迁移

### 步骤 1：在 WSL 中创建项目目录

```bash
# 在 WSL 中
cd ~
mkdir -p ~/tr-master
cd ~/tr-master
```

### 步骤 2：复制项目文件

**方法一：从 Windows 复制（推荐）**

```bash
# 在 WSL 中，Windows 的 C: 盘挂载在 /mnt/c/
cp -r /mnt/c/TR-master/TR\ UI ~/tr-master/
cp -r /mnt/c/TR-master/TR\ database ~/tr-master/
```

**方法二：使用 Git（如果项目在 Git 仓库中）**

```bash
cd ~/tr-master
git clone <your-repo-url> .
```

### 步骤 3：复制数据文件

```bash
# 创建 Stockist&Test Report 目录
mkdir -p ~/tr-master/stockist-test-report

# 从 Windows 复制文件（如果文件在 Windows 上）
# 注意：如果文件很大，考虑使用 rsync 或分批复制
rsync -av --progress /mnt/d/Stockist\&Test\ Report/ ~/tr-master/stockist-test-report/
```

### 步骤 4：设置文件权限

```bash
cd ~/tr-master
# 设置目录权限
chmod -R 755 "TR UI"
chmod -R 755 "TR database"
chmod -R 755 stockist-test-report

# 设置日志目录权限
mkdir -p "TR UI/backend/logs"
chmod 755 "TR UI/backend/logs"
```

---

## Python 环境配置

### 步骤 1：创建虚拟环境

```bash
cd ~/tr-master/TR\ UI/backend

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate
```

### 步骤 2：安装依赖

```bash
# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt

# 如果 WeasyPrint 安装失败，需要先安装系统依赖
sudo apt install -y \
    python3-dev \
    python3-cffi \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info
```

### 步骤 3：验证安装

```bash
# 检查关键包
python3 -c "import flask; print('Flask:', flask.__version__)"
python3 -c "import gunicorn; print('Gunicorn:', gunicorn.__version__)"
python3 -c "import weasyprint; print('WeasyPrint: OK')"
```

---

## 数据库和文件路径配置

### 步骤 1：检查数据库文件

```bash
# 检查数据库文件是否存在
ls -lh ~/tr-master/TR\ database/data_3years.db

# 如果数据库文件不存在，需要从 Windows 复制
cp /mnt/c/TR-master/TR\ database/data_3years.db ~/tr-master/TR\ database/
```

### 步骤 2：创建环境变量文件

```bash
cd ~/tr-master/TR\ UI/backend

# 创建 .env 文件
cat > .env << 'EOF'
# 数据库路径（WSL 路径）
DB_PATH=/home/$(whoami)/tr-master/TR database/data_3years.db

# Stockist&Test Report 文件夹路径（WSL 路径）
STOCKIST_TEST_FOLDER=/home/$(whoami)/tr-master/stockist-test-report

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

# 替换路径中的 $(whoami)
sed -i "s|\$(whoami)|$(whoami)|g" .env

# 查看配置
cat .env
```

### 步骤 3：验证路径

```bash
# 检查数据库文件
python3 -c "
import os
db_path = os.path.expanduser('~/tr-master/TR database/data_3years.db')
print(f'数据库路径: {db_path}')
print(f'数据库存在: {os.path.exists(db_path)}')
"

# 检查文件目录
ls -la ~/tr-master/stockist-test-report/
```

---

## Gunicorn 配置

### 步骤 1：检查配置文件

```bash
cd ~/tr-master/TR\ UI/backend

# 检查 gunicorn_config.py 是否存在
ls -la gunicorn_config.py

# 查看配置
cat gunicorn_config.py
```

### 步骤 2：调整 Gunicorn 配置（如需要）

编辑 `gunicorn_config.py`，确保路径正确：

```python
# 日志配置（使用 Linux 路径）
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"

# 工作进程数（根据 CPU 核心数自动计算）
workers = multiprocessing.cpu_count() * 2 + 1

# 临时目录（使用 Linux 内存文件系统）
worker_tmp_dir = "/dev/shm"
```

### 步骤 3：创建启动脚本

```bash
cd ~/tr-master/TR\ UI/backend

# 创建启动脚本
cat > start_gunicorn.sh << 'EOF'
#!/bin/bash
# TR Report System Gunicorn 启动脚本

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
EOF

# 设置执行权限
chmod +x start_gunicorn.sh
```

---

## Nginx 配置

### 步骤 1：安装 Nginx

```bash
sudo apt install -y nginx

# 检查 Nginx 状态
sudo systemctl status nginx
```

### 步骤 2：创建 Nginx 配置

```bash
# 创建配置文件
sudo nano /etc/nginx/sites-available/tr-report
```

配置文件内容：

```nginx
server {
    listen 80;
    server_name _;  # 接受所有域名和IP访问
    
    # 字符编码
    charset utf-8;
    
    # 前端静态文件服务
    location / {
        root /home/$(whoami)/tr-master/TR UI;
        index login.html;
        try_files $uri $uri/ /login.html;
    }
    
    # 后端 API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        
        # 基本代理头设置
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # HTTP 版本
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        
        # 超时设置（适应大文件下载和长时间处理）
        proxy_connect_timeout 1800s;
        proxy_send_timeout 1800s;
        proxy_read_timeout 1800s;
        
        # 缓冲设置
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
    }
    
    # 错误页面
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
```

**注意：** 将 `$(whoami)` 替换为你的实际用户名，或使用绝对路径。

### 步骤 3：启用配置

```bash
# 替换路径中的用户名
sudo sed -i "s|\$(whoami)|$(whoami)|g" /etc/nginx/sites-available/tr-report

# 创建符号链接
sudo ln -s /etc/nginx/sites-available/tr-report /etc/nginx/sites-enabled/

# 删除默认配置（可选）
sudo rm /etc/nginx/sites-enabled/default

# 测试配置
sudo nginx -t

# 如果测试通过，重载 Nginx
sudo systemctl reload nginx
```

---

## 服务启动和管理

### 方法一：手动启动（开发/测试）

```bash
cd ~/tr-master/TR\ UI/backend

# 激活虚拟环境
source venv/bin/activate

# 启动 Gunicorn
./start_gunicorn.sh

# 或者直接运行
gunicorn -c gunicorn_config.py tr_fill_in_api:app
```

### 方法二：使用 systemd 服务（生产环境推荐）

#### 创建 systemd 服务文件

```bash
sudo nano /etc/systemd/system/tr-report.service
```

服务文件内容：

```ini
[Unit]
Description=TR Report System Gunicorn Service
After=network.target

[Service]
Type=notify
User=你的用户名
Group=你的用户组
WorkingDirectory=/home/你的用户名/tr-master/TR UI/backend
Environment="PATH=/home/你的用户名/tr-master/TR UI/backend/venv/bin"
Environment="API_HOST=0.0.0.0"
Environment="API_PORT=5000"
Environment="DEBUG=False"
ExecStart=/home/你的用户名/tr-master/TR UI/backend/venv/bin/gunicorn \
    -c gunicorn_config.py \
    tr_fill_in_api:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**替换路径：**
```bash
# 获取用户名
USERNAME=$(whoami)

# 创建服务文件（自动替换）
sudo tee /etc/systemd/system/tr-report.service > /dev/null << EOF
[Unit]
Description=TR Report System Gunicorn Service
After=network.target

[Service]
Type=notify
User=$USERNAME
Group=$USERNAME
WorkingDirectory=/home/$USERNAME/tr-master/TR UI/backend
Environment="PATH=/home/$USERNAME/tr-master/TR UI/backend/venv/bin"
Environment="API_HOST=0.0.0.0"
Environment="API_PORT=5000"
Environment="DEBUG=False"
ExecStart=/home/$USERNAME/tr-master/TR UI/backend/venv/bin/gunicorn \\
    -c gunicorn_config.py \\
    tr_fill_in_api:app
ExecReload=/bin/kill -s HUP \\\$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

#### 启用和管理服务

```bash
# 重载 systemd
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable tr-report

# 启动服务
sudo systemctl start tr-report

# 查看状态
sudo systemctl status tr-report

# 查看日志
sudo journalctl -u tr-report -f

# 停止服务
sudo systemctl stop tr-report

# 重启服务
sudo systemctl restart tr-report
```

---

## 测试验证

### 步骤 1：检查服务状态

```bash
# 检查 Gunicorn 进程
ps aux | grep gunicorn

# 检查端口监听
netstat -tlnp | grep 5000
# 或
ss -tlnp | grep 5000

# 检查 Nginx 状态
sudo systemctl status nginx
```

### 步骤 2：测试 API

```bash
# 测试健康检查
curl http://localhost:5000/health

# 测试通过 Nginx
curl http://localhost/health

# 测试登录（需要先获取 token）
curl -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Vschk!8866"}'
```

### 步骤 3：测试前端访问

在浏览器中访问：
- `http://localhost/` 或 `http://你的WSL-IP/`
- 应该能看到登录页面

### 步骤 4：检查日志

```bash
# Gunicorn 访问日志
tail -f ~/tr-master/TR\ UI/backend/logs/gunicorn_access.log

# Gunicorn 错误日志
tail -f ~/tr-master/TR\ UI/backend/logs/gunicorn_error.log

# 应用日志
tail -f ~/tr-master/TR\ UI/backend/logs/app.log

# Nginx 访问日志
sudo tail -f /var/log/nginx/access.log

# Nginx 错误日志
sudo tail -f /var/log/nginx/error.log
```

---

## 常见问题

### 问题 1：端口被占用

```bash
# 检查端口占用
sudo lsof -i :5000
# 或
sudo netstat -tlnp | grep 5000

# 杀死占用进程
sudo kill -9 <PID>
```

### 问题 2：权限错误

```bash
# 检查文件权限
ls -la ~/tr-master/TR\ UI/backend/logs/

# 修复权限
chmod 755 ~/tr-master/TR\ UI/backend/logs/
chown -R $(whoami):$(whoami) ~/tr-master/
```

### 问题 3：数据库连接失败

```bash
# 检查数据库文件权限
ls -la ~/tr-master/TR\ database/data_3years.db

# 修复权限
chmod 644 ~/tr-master/TR\ database/data_3years.db
chown $(whoami):$(whoami) ~/tr-master/TR\ database/data_3years.db
```

### 问题 4：Nginx 502 Bad Gateway

```bash
# 检查 Gunicorn 是否运行
ps aux | grep gunicorn

# 检查 Gunicorn 日志
tail -50 ~/tr-master/TR\ UI/backend/logs/gunicorn_error.log

# 检查 Nginx 错误日志
sudo tail -50 /var/log/nginx/error.log
```

### 问题 5：文件路径问题

```bash
# 检查路径是否正确
python3 -c "
import os
from pathlib import Path
db_path = Path.home() / 'tr-master' / 'TR database' / 'data_3years.db'
print(f'数据库路径: {db_path}')
print(f'存在: {db_path.exists()}')
print(f'绝对路径: {db_path.resolve()}')
"
```

### 问题 6：WeasyPrint 安装失败

```bash
# 安装系统依赖
sudo apt install -y \
    python3-dev \
    python3-cffi \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation

# 重新安装 WeasyPrint
pip install --force-reinstall weasyprint
```

---

## 性能优化建议

### 1. 调整 Gunicorn 工作进程数

编辑 `gunicorn_config.py`：

```python
# 根据 CPU 核心数调整
import multiprocessing
cpu_count = multiprocessing.cpu_count()
workers = min(cpu_count * 2 + 1, 20)  # 最多20个进程
```

### 2. 使用 Redis 缓存（可选）

```bash
# 安装 Redis
sudo apt install -y redis-server

# 启动 Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# 在 .env 中启用
echo "REDIS_ENABLED=True" >> ~/tr-master/TR\ UI/backend/.env
```

### 3. 优化 Nginx

编辑 `/etc/nginx/nginx.conf`：

```nginx
# 在 http 块中添加
worker_processes auto;
worker_connections 1024;

# 启用 gzip
gzip on;
gzip_types text/plain text/css application/json application/javascript;
```

---

## 快速启动检查清单

- [ ] WSL2 已安装并更新
- [ ] 项目文件已复制到 WSL
- [ ] Python 虚拟环境已创建
- [ ] 所有依赖已安装
- [ ] 数据库文件已复制并设置权限
- [ ] `.env` 文件已配置正确路径
- [ ] Gunicorn 可以正常启动
- [ ] Nginx 已安装并配置
- [ ] systemd 服务已创建（如使用）
- [ ] 端口 80 和 5000 未被占用
- [ ] 防火墙规则已配置（如需要）
- [ ] 日志目录有写权限
- [ ] 前端可以正常访问
- [ ] API 可以正常响应

---

## 从 Windows 访问 WSL 服务

### 获取 WSL IP 地址

```bash
# 在 WSL 中
hostname -I
# 或
ip addr show eth0 | grep inet
```

### 在 Windows 浏览器中访问

- `http://WSL-IP地址/` （例如：`http://172.20.10.2/`）

### 配置 Windows 防火墙（如需要）

在 Windows PowerShell（管理员）中：

```powershell
# 允许 WSL 端口（如果需要）
New-NetFirewallRule -DisplayName "WSL TR Report" -Direction Inbound -LocalPort 80,5000 -Protocol TCP -Action Allow
```

---

## 下一步

1. ✅ 完成基础部署
2. 🔄 配置自动启动（systemd）
3. 🔄 设置日志轮转
4. 🔄 配置监控和告警
5. 🔄 定期备份数据库
6. 🔄 性能调优

---

**部署完成后，你的系统应该能够：**
- ✅ 处理更多并发用户
- ✅ 减少卡顿问题
- ✅ 更稳定的长期运行
- ✅ 更好的性能表现

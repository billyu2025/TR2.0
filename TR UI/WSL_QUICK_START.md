# WSL 部署快速开始

## 🚀 快速部署（5分钟）

### 方法一：使用自动部署脚本（推荐）

```bash
# 1. 进入 WSL
wsl

# 2. 复制项目文件（如果还没有）
mkdir -p ~/tr-master
cp -r /mnt/c/TR-master/TR\ UI ~/tr-master/
cp -r /mnt/c/TR-master/TR\ database ~/tr-master/

# 3. 运行部署脚本
cd ~/tr-master/TR\ UI/backend
bash wsl_deploy.sh
```

### 方法二：手动部署

```bash
# 1. 进入 WSL 并创建目录
wsl
mkdir -p ~/tr-master
cd ~/tr-master

# 2. 复制项目文件
cp -r /mnt/c/TR-master/TR\ UI .
cp -r /mnt/c/TR-master/TR\ database .

# 3. 安装系统依赖
sudo apt update
sudo apt install -y python3-pip python3-venv nginx \
    python3-dev libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info fonts-liberation

# 4. 创建虚拟环境并安装依赖
cd "TR UI/backend"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. 创建 .env 文件
cat > .env << EOF
DB_PATH=/home/$(whoami)/tr-master/TR database/data_3years.db
STOCKIST_TEST_FOLDER=/home/$(whoami)/tr-master/stockist-test-report
API_HOST=0.0.0.0
API_PORT=5000
DEBUG=False
SESSION_TTL_HOURS=24
PASSWORD_ITERATIONS=120000
REDIS_ENABLED=False
EOF

# 6. 创建日志目录
mkdir -p logs
chmod 755 logs

# 7. 配置 Nginx（参考 WSL_DEPLOYMENT_GUIDE.md）

# 8. 启动服务
./start_gunicorn.sh
```

---

## 📝 关键路径配置

### WSL 路径映射

| Windows 路径 | WSL 路径 |
|------------|---------|
| `C:\TR-master\TR UI` | `/home/用户名/tr-master/TR UI` |
| `C:\TR-master\TR database` | `/home/用户名/tr-master/TR database` |
| `D:\Stockist&Test Report` | `/home/用户名/tr-master/stockist-test-report` |

### 环境变量示例

```bash
# .env 文件
DB_PATH=/home/yourusername/tr-master/TR database/data_3years.db
STOCKIST_TEST_FOLDER=/home/yourusername/tr-master/stockist-test-report
API_HOST=0.0.0.0
API_PORT=5000
DEBUG=False
```

---

## 🔧 常用命令

### 启动服务

```bash
# 手动启动（开发/测试）
cd ~/tr-master/TR\ UI/backend
source venv/bin/activate
./start_gunicorn.sh

# 或直接运行
gunicorn -c gunicorn_config.py tr_fill_in_api:app
```

### 停止服务

```bash
# 查找进程
ps aux | grep gunicorn

# 停止进程
pkill -f gunicorn
# 或
kill <PID>
```

### 查看日志

```bash
# Gunicorn 访问日志
tail -f ~/tr-master/TR\ UI/backend/logs/gunicorn_access.log

# Gunicorn 错误日志
tail -f ~/tr-master/TR\ UI/backend/logs/gunicorn_error.log

# Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 测试服务

```bash
# 测试后端 API
curl http://localhost:5000/health

# 测试 Nginx 代理
curl http://localhost/health

# 获取 WSL IP
hostname -I
```

---

## 🌐 从 Windows 访问

### 获取 WSL IP 地址

```bash
# 在 WSL 中运行
hostname -I
# 输出示例: 172.20.10.2
```

### 在 Windows 浏览器中访问

- `http://172.20.10.2/` （替换为你的 WSL IP）

### 配置 Windows 防火墙（如需要）

```powershell
# 在 PowerShell (管理员) 中
New-NetFirewallRule -DisplayName "WSL TR Report" -Direction Inbound -LocalPort 80,5000 -Protocol TCP -Action Allow
```

---

## ⚙️ 使用 systemd 服务（生产环境）

### 创建服务文件

```bash
# 获取用户名
USERNAME=$(whoami)

# 创建服务文件
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

### 管理服务

```bash
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

## 🐛 常见问题

### 1. 端口被占用

```bash
# 检查端口
sudo lsof -i :5000
sudo netstat -tlnp | grep 5000

# 停止占用进程
sudo kill -9 <PID>
```

### 2. 权限错误

```bash
# 修复权限
chmod 755 ~/tr-master/TR\ UI/backend/logs/
chown -R $(whoami):$(whoami) ~/tr-master/
```

### 3. Nginx 502 Bad Gateway

```bash
# 检查 Gunicorn 是否运行
ps aux | grep gunicorn

# 检查日志
tail -50 ~/tr-master/TR\ UI/backend/logs/gunicorn_error.log
sudo tail -50 /var/log/nginx/error.log
```

### 4. 数据库连接失败

```bash
# 检查数据库文件
ls -la ~/tr-master/TR\ database/data_3years.db

# 修复权限
chmod 644 ~/tr-master/TR\ database/data_3years.db
```

---

## 📚 详细文档

- **完整部署指南**: `WSL_DEPLOYMENT_GUIDE.md`
- **Gunicorn 使用指南**: `backend/GUNICORN_USAGE_GUIDE.md`
- **部署检查清单**: `DEPLOYMENT_CHECKLIST.md`

---

## ✅ 部署检查清单

- [ ] WSL2 已安装
- [ ] 项目文件已复制到 WSL
- [ ] Python 虚拟环境已创建
- [ ] 所有依赖已安装
- [ ] `.env` 文件已配置
- [ ] 数据库文件已复制
- [ ] Nginx 已配置
- [ ] Gunicorn 可以启动
- [ ] 端口 80 和 5000 未被占用
- [ ] 可以从 Windows 浏览器访问

---

**部署完成后，系统应该能够：**
- ✅ 处理更多并发用户
- ✅ 减少卡顿问题
- ✅ 更稳定的长期运行
- ✅ 更好的性能表现

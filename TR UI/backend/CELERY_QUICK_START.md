# Celery + Redis 快速开始指南

## 5 分钟快速部署

### 步骤 1：安装依赖（2 分钟）

```powershell
cd "C:\TR-master\TR UI\backend"
pip install celery redis eventlet
```

### 步骤 2：安装 Redis（2 分钟）

#### 选项 A：使用 WSL（推荐）

```bash
# 在 WSL 中
sudo apt update
sudo apt install redis-server
sudo service redis-server start

# 验证
redis-cli ping
# 应该返回: PONG
```

#### 选项 B：使用 Memurai（Windows 原生）

1. 下载：https://www.memurai.com/
2. 安装后自动运行

### 步骤 3：启动 Celery Worker（1 分钟）

**Windows：**
```powershell
cd "C:\TR-master\TR UI\backend"
.\start_celery_worker.bat
```

**Linux/WSL：**
```bash
cd "/mnt/c/TR-master/TR UI/backend"
chmod +x start_celery_worker.sh
./start_celery_worker.sh
```

### 步骤 4：测试

```python
# 测试脚本
from celery_tasks import generate_pdf_task

# 启动任务
task = generate_pdf_task.delay(123456)
print(f"任务ID: {task.id}")

# 查询状态
print(f"状态: {task.state}")

# 等待结果
result = task.get(timeout=60)
print(f"结果: {result}")
```

---

## 使用 Celery 版本的 API

### 修改 API 端点（可选）

如果你想使用 Celery 而不是 Threading，修改 `tr_fill_in_api.py`：

```python
# 在文件顶部添加
from celery_tasks import generate_pdf_task

# 修改 /api/pdf/generate 端点
@app.route('/api/pdf/generate', methods=['POST'])
@require_auth()
def generate_pdf():
    """创建 PDF 生成任务（使用 Celery）"""
    try:
        current_user = g.current_user
        data = request.json
        order_no = data.get('order_no')
        
        if not order_no:
            return jsonify({
                'success': False,
                'error': 'Order No is required'
            }), 400
        
        # 启动 Celery 任务
        task = generate_pdf_task.delay(int(order_no))
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'order_no': order_no,
            'message': 'PDF 生成任务已创建，正在后台处理'
        }), 202
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pdf/task-status/<task_id>', methods=['GET'])
@require_auth()
def get_pdf_task_status(task_id):
    """查询 PDF 生成任务状态（使用 Celery）"""
    try:
        from celery_tasks import generate_pdf_task
        
        task = generate_pdf_task.AsyncResult(task_id)
        
        if task.state == 'PENDING':
            response = {
                'success': True,
                'status': 'pending',
                'progress': 0,
                'message': '任务等待中...'
            }
        elif task.state == 'PROGRESS':
            meta = task.info or {}
            response = {
                'success': True,
                'status': 'processing',
                'progress': meta.get('progress', 0),
                'message': meta.get('message', '处理中...')
            }
        elif task.state == 'SUCCESS':
            result = task.result or {}
            response = {
                'success': True,
                'status': 'completed',
                'progress': 100,
                'message': 'PDF 生成完成',
                'pdf_path': result.get('pdf_path'),
                'pdf_status': 'generated'
            }
        else:
            error_info = str(task.info) if task.info else '未知错误'
            response = {
                'success': True,
                'status': 'failed',
                'progress': 0,
                'message': f'PDF 生成失败: {error_info}',
                'error_message': error_info,
                'pdf_status': 'failed'
            }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
```

---

## 使用 NSSM 管理 Celery Worker（Windows）

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"
$pythonPath = "C:\Python39\python.exe"  # 替换为你的 Python 路径
$workDir = "C:\TR-master\TR UI\backend"

# 安装服务
& $nssm install TR-CeleryWorker $pythonPath "-m celery -A celery_app worker --pool=eventlet --concurrency=4 --loglevel=info"
& $nssm set TR-CeleryWorker AppDirectory $workDir
& $nssm set TR-CeleryWorker DisplayName "TR Backend Celery Worker"
& $nssm set TR-CeleryWorker Start SERVICE_AUTO_START

# 设置日志
& $nssm set TR-CeleryWorker AppStdout "$workDir\logs\celery_output.log"
& $nssm set TR-CeleryWorker AppStderr "$workDir\logs\celery_error.log"

# 启动服务
& $nssm start TR-CeleryWorker
```

---

## 验证安装

### 1. 检查 Redis

```powershell
python -c "import redis; r = redis.Redis(); print('Redis:', 'OK' if r.ping() else 'FAIL')"
```

### 2. 检查 Celery

```powershell
celery -A celery_app inspect ping
```

### 3. 测试任务

```python
from celery_tasks import generate_pdf_task
task = generate_pdf_task.delay(123456)
print(task.id)
```

---

## 常见问题

### Q: Redis 连接失败？

**A:** 检查 Redis 是否运行：
```powershell
redis-cli ping
```

### Q: Celery Worker 无法启动（Windows）？

**A:** 使用 eventlet 池：
```powershell
celery -A celery_app worker --pool=eventlet --concurrency=4
```

### Q: 任务一直处于 PENDING？

**A:** 检查 Worker 是否运行，查看日志。

---

## 下一步

- 查看详细文档：`CELERY_REDIS_IMPLEMENTATION.md`
- 配置监控：安装 Flower
- 优化性能：调整 Worker 数量

---

**完成！现在你可以使用 Celery + Redis 了！**

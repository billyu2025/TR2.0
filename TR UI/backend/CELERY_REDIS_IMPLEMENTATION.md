# Celery + Redis 异步任务队列实施指南

## 概述

Celery + Redis 是一个专业的分布式任务队列系统，比简单的 threading 方案更强大，提供：
- ✅ 任务持久化（服务重启不丢失）
- ✅ 任务重试机制
- ✅ 任务优先级和路由
- ✅ 更好的监控和管理
- ✅ 支持分布式部署

## 方案对比

| 特性 | Threading（当前） | Celery + Redis |
|------|------------------|----------------|
| 实施难度 | ⭐ 简单 | ⭐⭐⭐ 中等 |
| 任务持久化 | ❌ 无 | ✅ 有 |
| 任务重试 | ❌ 无 | ✅ 有 |
| 监控管理 | ⭐ 基础 | ⭐⭐⭐⭐⭐ 专业 |
| 分布式支持 | ❌ 无 | ✅ 有 |
| 资源占用 | 低 | 中等（需要 Redis） |

---

## 步骤 1：安装依赖

### 1.1 安装 Python 包

```powershell
cd "C:\TR-master\TR UI\backend"
pip install celery redis
```

**Windows 特殊要求：**

Celery 在 Windows 上需要额外的包：

```powershell
# 方法 1：使用 eventlet（推荐，简单）
pip install eventlet

# 方法 2：使用 gevent（性能更好）
pip install gevent
```

### 1.2 安装 Redis

#### 选项 A：使用 WSL（推荐）

如果已安装 WSL，在 WSL 中运行：

```bash
# 在 WSL 中
sudo apt update
sudo apt install redis-server

# 启动 Redis
sudo service redis-server start

# 验证
redis-cli ping
# 应该返回: PONG
```

#### 选项 B：使用 Memurai（Windows 原生 Redis）

1. 下载：https://www.memurai.com/
2. 安装后自动作为 Windows 服务运行
3. 默认端口：6379

#### 选项 C：使用 Docker

```powershell
docker run -d -p 6379:6379 --name redis redis:latest
```

#### 选项 D：使用 Redis for Windows（不推荐，已停止维护）

---

## 步骤 2：创建 Celery 应用

创建 `backend/celery_app.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Celery 应用配置
"""

from celery import Celery
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Redis 配置
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# 构建 Redis URL
if REDIS_PASSWORD:
    redis_url = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'
else:
    redis_url = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'

# 创建 Celery 应用
celery_app = Celery(
    'tr_backend',
    broker=redis_url,
    backend=redis_url
)

# Celery 配置
celery_app.conf.update(
    # 任务序列化
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # 时区
    timezone='UTC',
    enable_utc=True,
    
    # 任务跟踪
    task_track_started=True,
    task_send_sent_event=True,
    
    # 任务超时
    task_time_limit=30 * 60,  # 30 分钟硬超时
    task_soft_time_limit=25 * 60,  # 25 分钟软超时
    
    # Worker 配置
    worker_prefetch_multiplier=1,  # 防止任务堆积
    worker_max_tasks_per_child=50,  # 防止内存泄漏
    
    # 结果过期时间
    result_expires=3600,  # 1 小时后过期
    
    # 任务路由（可选）
    task_routes={
        'tasks.generate_pdf': {'queue': 'pdf'},
        'tasks.batch_download': {'queue': 'download'},
    },
    
    # 任务优先级（可选）
    task_default_priority=5,
    
    # 任务重试配置
    task_acks_late=True,  # 任务完成后才确认
    task_reject_on_worker_lost=True,  # Worker 崩溃时重新排队
)

# 自动发现任务
celery_app.autodiscover_tasks(['tasks'])

print(f"[Celery] 已配置，Redis: {redis_url}")
```

---

## 步骤 3：创建任务定义

创建 `backend/celery_tasks.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Celery 任务定义
"""

from celery_app import celery_app
import os
import sys
from datetime import datetime


@celery_app.task(bind=True, name='tasks.generate_pdf')
def generate_pdf_task(self, order_no):
    """
    异步生成 PDF 任务
    
    Args:
        order_no: 订单号
        
    Returns:
        dict: 包含成功状态和 PDF 路径的字典
    """
    try:
        # 更新任务状态
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 10,
                'message': '正在初始化 PDF 生成器...'
            }
        )
        
        # 导入PDF生成器 - 添加TR database目录到路径
        db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'TR database'))
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        
        from generate_landscape_pdf import OrderTraceabilityPDFGenerator
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 20,
                'message': '正在创建 PDF 生成器...'
            }
        )
        
        # 创建PDF生成器
        generator = OrderTraceabilityPDFGenerator()
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 30,
                'message': '正在生成 PDF...'
            }
        )
        
        # 生成PDF
        success, pdf_path = generator.generate_pdf(int(order_no))
        
        if success:
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': 90,
                    'message': 'PDF 生成完成，正在更新状态...'
                }
            )
            
            # 更新 PDF_Status 表
            from tr_fill_in_api import get_db_connection, cache
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO PDF_Status 
                    (Order_No, pdf_status, pdf_path, generated_at, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (order_no, 'generated', pdf_path))
                
                conn.commit()
                
                # 失效订单列表缓存
                try:
                    cache.delete('orders:list:*')
                except Exception:
                    pass
                
                print(f"[Celery PDF任务] PDF_Status updated for Order {order_no}: generated")
                
            except Exception as db_error:
                print(f"[Celery PDF任务] Failed to update PDF_Status: {db_error}")
                conn.rollback()
            finally:
                conn.close()
            
            return {
                'success': True,
                'order_no': order_no,
                'pdf_path': pdf_path,
                'progress': 100,
                'message': 'PDF 生成成功'
            }
        else:
            # 更新 PDF_Status 表为失败
            from tr_fill_in_api import get_db_connection, cache
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO PDF_Status 
                    (Order_No, pdf_status, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (order_no, 'failed'))
                
                conn.commit()
                
                try:
                    cache.delete('orders:list:*')
                except Exception:
                    pass
                
            except Exception as db_error:
                print(f"[Celery PDF任务] Failed to update PDF_Status: {db_error}")
                conn.rollback()
            finally:
                conn.close()
            
            error_msg = f'Order {order_no} not found in database'
            raise Exception(error_msg)
            
    except Exception as e:
        error_msg = str(e)
        print(f"[Celery PDF任务] 任务失败: Order {order_no}, 错误: {error_msg}")
        
        # 更新 PDF_Status 表为失败
        try:
            from tr_fill_in_api import get_db_connection, cache
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO PDF_Status 
                (Order_No, pdf_status, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (order_no, 'failed'))
            conn.commit()
            
            try:
                cache.delete('orders:list:*')
            except Exception:
                pass
            
            conn.close()
        except:
            pass
        
        # 重新抛出异常，让 Celery 处理重试
        raise


@celery_app.task(bind=True, name='tasks.batch_download')
def batch_download_task(self, order_nos, user_id, task_type='order'):
    """
    异步批量下载任务
    
    Args:
        order_nos: 订单号列表
        user_id: 用户ID
        task_type: 任务类型（'order', 'dd_no', 'date'）
        
    Returns:
        dict: 包含成功状态和 ZIP 路径的字典
    """
    try:
        from download_task_manager import DownloadTaskManager
        import os
        
        total = len(order_nos)
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 0,
                'message': f'开始处理 {total} 个订单...',
                'total': total,
                'processed': 0
            }
        )
        
        # 获取基础文件夹路径
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        
        # 创建任务管理器
        from tr_fill_in_api import DB_PATH
        task_manager = DownloadTaskManager(DB_PATH, base_folder)
        
        # 创建任务记录（用于跟踪）
        request_params = {'order_nos': order_nos}
        task_id = task_manager.create_task(user_id, task_type, request_params)
        
        # 处理任务
        task_manager.process_task(task_id, task_type, request_params)
        
        # 获取任务状态
        task_status = task_manager.get_task_status(task_id, user_id)
        
        if task_status and task_status['status'] == 'completed':
            return {
                'success': True,
                'task_id': task_id,
                'zip_path': task_status['zip_path'],
                'zip_size': task_status['zip_size'],
                'file_count': task_status.get('processed_files', 0),
                'progress': 100,
                'message': '下载完成'
            }
        else:
            error_msg = task_status.get('error_message', '下载失败') if task_status else '任务不存在'
            raise Exception(error_msg)
            
    except Exception as e:
        error_msg = str(e)
        print(f"[Celery 下载任务] 任务失败: {error_msg}")
        raise
```

---

## 步骤 4：修改 API 端点

修改 `tr_fill_in_api.py` 中的 PDF 生成端点：

```python
# 在文件顶部添加导入
from celery_tasks import generate_pdf_task

# 修改 /api/pdf/generate 端点
@app.route('/api/pdf/generate', methods=['POST'])
@require_auth()
def generate_pdf():
    """
    创建 PDF 生成任务（使用 Celery）
    """
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
        }), 202  # 202 Accepted
        
    except Exception as e:
        import traceback
        print(f"[错误] 创建 PDF 任务失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pdf/task-status/<task_id>', methods=['GET'])
@require_auth()
def get_pdf_task_status(task_id):
    """
    查询 PDF 生成任务状态（使用 Celery）
    """
    try:
        from celery_tasks import generate_pdf_task
        
        # 获取任务结果
        task = generate_pdf_task.AsyncResult(task_id)
        
        if task.state == 'PENDING':
            # 任务等待中
            response = {
                'success': True,
                'task_id': task_id,
                'status': 'pending',
                'progress': 0,
                'message': '任务等待中...'
            }
        elif task.state == 'PROGRESS':
            # 任务处理中
            meta = task.info or {}
            response = {
                'success': True,
                'task_id': task_id,
                'status': 'processing',
                'progress': meta.get('progress', 0),
                'message': meta.get('message', '处理中...')
            }
        elif task.state == 'SUCCESS':
            # 任务成功
            result = task.result or {}
            response = {
                'success': True,
                'task_id': task_id,
                'status': 'completed',
                'progress': 100,
                'message': 'PDF 生成完成',
                'pdf_path': result.get('pdf_path'),
                'pdf_status': 'generated',
                'order_no': result.get('order_no')
            }
        else:  # FAILURE 或其他状态
            # 任务失败
            error_info = task.info if isinstance(task.info, str) else str(task.info) if task.info else '未知错误'
            response = {
                'success': True,
                'task_id': task_id,
                'status': 'failed',
                'progress': 0,
                'message': f'PDF 生成失败: {error_info}',
                'error_message': error_info,
                'pdf_status': 'failed'
            }
        
        return jsonify(response)
        
    except Exception as e:
        import traceback
        print(f"[错误] 查询 PDF 任务状态失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
```

---

## 步骤 5：启动 Celery Worker

### 5.1 Windows 启动（使用 eventlet）

```powershell
cd "C:\TR-master\TR UI\backend"
celery -A celery_app worker --pool=eventlet --concurrency=4 --loglevel=info
```

### 5.2 Linux/WSL 启动（使用 prefork）

```bash
cd "/mnt/c/TR-master/TR UI/backend"
celery -A celery_app worker --concurrency=4 --loglevel=info
```

### 5.3 使用 NSSM 管理 Celery Worker（Windows）

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"
$pythonPath = "C:\Python39\python.exe"  # 替换为你的 Python 路径
$workDir = "C:\TR-master\TR UI\backend"

# 安装 Celery Worker 服务
& $nssm install TR-CeleryWorker $pythonPath "-m celery -A celery_app worker --pool=eventlet --concurrency=4 --loglevel=info"
& $nssm set TR-CeleryWorker AppDirectory $workDir
& $nssm set TR-CeleryWorker DisplayName "TR Backend Celery Worker"
& $nssm set TR-CeleryWorker Description "TR Backend Celery Worker for async tasks"
& $nssm set TR-CeleryWorker Start SERVICE_AUTO_START

# 设置环境变量
& $nssm set TR-CeleryWorker AppEnvironmentExtra "REDIS_HOST=localhost" "REDIS_PORT=6379"

# 设置日志
& $nssm set TR-CeleryWorker AppStdout "$workDir\logs\celery_output.log"
& $nssm set TR-CeleryWorker AppStderr "$workDir\logs\celery_error.log"

# 启动服务
& $nssm start TR-CeleryWorker
```

---

## 步骤 6：监控和管理

### 6.1 使用 Flower（Web 监控界面）

```powershell
pip install flower
```

启动 Flower：

```powershell
celery -A celery_app flower
```

访问：http://localhost:5555

### 6.2 使用命令行监控

```powershell
# 查看活动任务
celery -A celery_app inspect active

# 查看注册的任务
celery -A celery_app inspect registered

# 查看 Worker 状态
celery -A celery_app inspect stats
```

---

## 步骤 7：环境变量配置

在 `.env` 文件中添加：

```env
# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Celery 配置（可选）
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

---

## 步骤 8：测试

### 8.1 测试 Redis 连接

```python
import redis

r = redis.Redis(host='localhost', port=6379, db=0)
print(r.ping())  # 应该返回 True
```

### 8.2 测试 Celery 任务

```python
from celery_tasks import generate_pdf_task

# 启动任务
task = generate_pdf_task.delay(123456)

# 查询状态
print(f"任务ID: {task.id}")
print(f"状态: {task.state}")

# 等待结果（同步）
result = task.get(timeout=60)
print(f"结果: {result}")
```

---

## 与现有 Threading 方案的对比

### 迁移建议

1. **如果已使用 Threading 方案**：
   - 可以保留 Threading 方案作为备选
   - 逐步迁移到 Celery
   - 两者可以共存

2. **新项目**：
   - 直接使用 Celery + Redis
   - 更专业、更可靠

### 功能对比

| 功能 | Threading | Celery |
|------|-----------|--------|
| 任务持久化 | ❌ | ✅ |
| 服务重启恢复 | ❌ | ✅ |
| 任务重试 | ❌ | ✅ |
| 任务优先级 | ❌ | ✅ |
| 分布式部署 | ❌ | ✅ |
| 监控界面 | ❌ | ✅ (Flower) |
| 资源占用 | 低 | 中等 |

---

## 故障排除

### 问题 1：Redis 连接失败

**错误：** `ConnectionError: Error connecting to Redis`

**解决方法：**
1. 检查 Redis 是否运行：`redis-cli ping`
2. 检查防火墙设置
3. 验证 Redis 配置（host, port, password）

### 问题 2：Celery Worker 无法启动（Windows）

**错误：** `NotImplementedError: Windows does not support fork()`

**解决方法：**
```powershell
# 使用 eventlet
celery -A celery_app worker --pool=eventlet --concurrency=4
```

### 问题 3：任务一直处于 PENDING 状态

**可能原因：**
- Worker 未运行
- 任务路由错误
- Redis 连接问题

**解决方法：**
1. 检查 Worker 是否运行
2. 检查任务路由配置
3. 查看 Worker 日志

---

## 性能优化建议

1. **Worker 数量**：
   - CPU 核心数 × 2
   - 例如：4 核 CPU → 8 个 Worker

2. **任务超时**：
   - PDF 生成：30 分钟
   - 批量下载：60 分钟

3. **结果过期**：
   - 设置合理的结果过期时间
   - 避免 Redis 内存占用过大

4. **任务优先级**：
   - 高优先级：用户请求的 PDF 生成
   - 低优先级：批量任务

---

## 总结

Celery + Redis 提供了专业的异步任务队列解决方案，适合：
- ✅ 需要任务持久化的场景
- ✅ 需要任务重试的场景
- ✅ 需要监控和管理的场景
- ✅ 需要分布式部署的场景

如果只是简单的异步处理，Threading 方案已经足够。如果需要更强大的功能，建议使用 Celery + Redis。

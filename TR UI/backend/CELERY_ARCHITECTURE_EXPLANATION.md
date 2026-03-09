# Celery Worker 与 Flask API 的关系说明

## 架构概览

```
┌─────────────────┐         ┌──────────────┐         ┌─────────────────┐
│   前端浏览器     │ ──────► │ Flask API    │ ──────► │  Celery Worker  │
│                 │         │ (tr_fill_in_ │         │  (后台进程)     │
│                 │         │   _api.py)   │         │                 │
└─────────────────┘         └──────────────┘         └─────────────────┘
                                      │                        │
                                      │                        │
                                      ▼                        ▼
                              ┌──────────────┐         ┌──────────────┐
                              │   SQLite DB  │         │    Redis     │
                              │              │         │  (任务队列)   │
                              └──────────────┘         └──────────────┘
```

## 关系说明

### 1. Flask API (`tr_fill_in_api.py`) - 请求处理层

**职责：**
- ✅ 接收 HTTP 请求
- ✅ 验证用户身份
- ✅ 创建 Celery 任务
- ✅ 立即返回任务 ID（不等待任务完成）
- ✅ 提供任务状态查询接口

**特点：**
- 轻量级，快速响应
- 不执行耗时操作
- 只负责任务调度

### 2. Celery Worker - 任务执行层

**职责：**
- ✅ 从 Redis 队列中获取任务
- ✅ 执行耗时操作（PDF 生成、批量下载等）
- ✅ 更新任务进度和状态
- ✅ 将结果存储到 Redis

**特点：**
- 独立进程运行
- 可以运行多个 Worker（并行处理）
- 不阻塞 Flask API

### 3. Redis - 消息队列

**职责：**
- ✅ 存储待执行的任务
- ✅ 存储任务结果
- ✅ 任务状态管理

**特点：**
- 任务持久化（服务重启不丢失）
- 支持任务优先级
- 支持任务重试

---

## 工作流程

### 场景 1：PDF 生成（使用 Celery）

```
1. 前端请求
   POST /api/pdf/generate
   { "order_no": 123456 }

2. Flask API (tr_fill_in_api.py)
   - 验证用户身份
   - 创建 Celery 任务
   - 将任务发送到 Redis 队列
   - 立即返回任务 ID
   
   响应：{ "task_id": "abc123", "status": "pending" }

3. Celery Worker
   - 从 Redis 队列获取任务
   - 执行 PDF 生成（耗时 10-60 秒）
   - 更新任务进度（10% → 20% → ... → 100%）
   - 将结果存储到 Redis

4. 前端轮询
   GET /api/pdf/task-status/abc123
   
   Flask API 从 Redis 获取任务状态并返回
```

### 场景 2：当前实现（使用 Threading）

```
1. 前端请求
   POST /api/pdf/generate
   { "order_no": 123456 }

2. Flask API (tr_fill_in_api.py)
   - 验证用户身份
   - 创建任务记录（pdf_tasks 表）
   - 启动后台线程
   - 立即返回任务 ID
   
   响应：{ "task_id": "abc123", "status": "pending" }

3. 后台线程（在 Flask 进程中）
   - 执行 PDF 生成（耗时 10-60 秒）
   - 更新任务状态（pdf_tasks 表）

4. 前端轮询
   GET /api/pdf/task-status/abc123
   
   Flask API 从 pdf_tasks 表查询状态并返回
```

---

## 两种方案对比

### 当前实现（Threading）

| 组件 | 位置 | 数据存储 |
|------|------|---------|
| Flask API | `tr_fill_in_api.py` | - |
| 任务管理器 | `pdf_task_manager.py` | SQLite (`pdf_tasks` 表) |
| 任务执行 | 后台线程（同一进程） | - |

**优点：**
- ✅ 简单，无需额外基础设施
- ✅ 快速实施
- ✅ 与现有代码兼容

**缺点：**
- ❌ 任务不持久化（服务重启丢失）
- ❌ 无任务重试机制
- ❌ 资源管理较简单

### Celery 方案

| 组件 | 位置 | 数据存储 |
|------|------|---------|
| Flask API | `tr_fill_in_api.py` | - |
| Celery 应用 | `celery_app.py` | Redis |
| 任务定义 | `celery_tasks.py` | Redis |
| 任务执行 | Celery Worker（独立进程） | Redis |

**优点：**
- ✅ 任务持久化（服务重启不丢失）
- ✅ 支持任务重试
- ✅ 更好的监控和管理
- ✅ 支持分布式部署

**缺点：**
- ⚠️ 需要安装 Redis
- ⚠️ 需要运行额外的 Worker 进程
- ⚠️ 实施复杂度稍高

---

## 代码关系

### 当前实现（Threading）

**`tr_fill_in_api.py` 中的相关代码：**

```python
@app.route('/api/pdf/generate', methods=['POST'])
def generate_pdf():
    # 1. 创建任务（存储在 SQLite）
    task_manager = PDFTaskManager(DB_PATH)
    task_id = task_manager.create_task(user_id, order_no)
    
    # 2. 启动后台线程（在 Flask 进程中）
    def process_task_async():
        task_manager.process_task(task_id, order_no)
    
    thread = threading.Thread(target=process_task_async, daemon=True)
    thread.start()
    
    # 3. 立即返回
    return jsonify({'task_id': task_id}), 202
```

**关系：**
- Flask API 直接调用 `PDFTaskManager`
- 任务存储在 SQLite (`pdf_tasks` 表)
- 任务在 Flask 进程的后台线程中执行

### Celery 方案

**`tr_fill_in_api.py` 中的相关代码：**

```python
from celery_tasks import generate_pdf_task

@app.route('/api/pdf/generate', methods=['POST'])
def generate_pdf():
    # 1. 创建 Celery 任务（发送到 Redis）
    task = generate_pdf_task.delay(order_no)
    
    # 2. 立即返回任务 ID
    return jsonify({'task_id': task.id}), 202
```

**`celery_tasks.py` 中的任务定义：**

```python
@celery_app.task(bind=True, name='tasks.generate_pdf')
def generate_pdf_task(self, order_no):
    # 这个函数在 Celery Worker 进程中执行
    # 不在 Flask 进程中执行
    generator = OrderTraceabilityPDFGenerator()
    success, pdf_path = generator.generate_pdf(order_no)
    return {'success': success, 'pdf_path': pdf_path}
```

**关系：**
- Flask API 调用 `generate_pdf_task.delay()` 将任务发送到 Redis
- Celery Worker 从 Redis 获取任务并执行
- 任务状态存储在 Redis
- Flask API 通过 `AsyncResult` 查询任务状态

---

## 进程关系

### Threading 方案

```
┌─────────────────────────────────────┐
│      Flask 进程 (tr_fill_in_api)    │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │ 主线程       │  │ 后台线程    │ │
│  │ (处理请求)   │  │ (执行任务)  │ │
│  └──────────────┘  └─────────────┘ │
│                                     │
│  ┌───────────────────────────────┐ │
│  │ SQLite (pdf_tasks 表)         │ │
│  └───────────────────────────────┘ │
└─────────────────────────────────────┘
```

**特点：**
- 所有操作在同一个进程中
- 任务在后台线程中执行
- 服务重启时，正在执行的任务会丢失

### Celery 方案

```
┌─────────────────────┐         ┌─────────────────────┐
│  Flask 进程          │         │  Celery Worker 进程  │
│  (tr_fill_in_api)   │         │  (celery worker)    │
│                     │         │                     │
│  ┌───────────────┐  │         │  ┌───────────────┐  │
│  │ 主线程        │  │         │  │ Worker 线程   │  │
│  │ (处理请求)    │  │         │  │ (执行任务)    │  │
│  └───────────────┘  │         │  └───────────────┘  │
└─────────────────────┘         └─────────────────────┘
         │                                  │
         │                                  │
         └──────────┬───────────────────────┘
                    │
                    ▼
            ┌───────────────┐
            │    Redis      │
            │  (任务队列)    │
            └───────────────┘
```

**特点：**
- Flask 和 Worker 是独立的进程
- 任务通过 Redis 队列传递
- 服务重启时，任务不会丢失（存储在 Redis）

---

## 如何选择

### 使用 Threading（当前实现）

**适合：**
- ✅ 简单场景
- ✅ 不需要任务持久化
- ✅ 不需要任务重试
- ✅ 快速实施

**当前状态：**
- 已实现并运行
- PDF 生成已异步化
- 下载任务已异步化

### 使用 Celery

**适合：**
- ✅ 需要任务持久化
- ✅ 需要任务重试
- ✅ 需要更好的监控
- ✅ 需要分布式部署

**实施步骤：**
1. 安装 Redis
2. 启动 Celery Worker
3. 修改 `tr_fill_in_api.py` 使用 Celery 任务

---

## 迁移示例

### 从 Threading 迁移到 Celery

**修改前（Threading）：**

```python
# tr_fill_in_api.py
from pdf_task_manager import PDFTaskManager

@app.route('/api/pdf/generate', methods=['POST'])
def generate_pdf():
    task_manager = PDFTaskManager(DB_PATH)
    task_id = task_manager.create_task(user_id, order_no)
    
    def process_task_async():
        task_manager.process_task(task_id, order_no)
    
    thread = threading.Thread(target=process_task_async, daemon=True)
    thread.start()
    
    return jsonify({'task_id': task_id}), 202
```

**修改后（Celery）：**

```python
# tr_fill_in_api.py
from celery_tasks import generate_pdf_task

@app.route('/api/pdf/generate', methods=['POST'])
def generate_pdf():
    # 直接调用 Celery 任务
    task = generate_pdf_task.delay(order_no)
    
    return jsonify({'task_id': task.id}), 202
```

**任务状态查询也需要修改：**

```python
# 修改前（Threading）
from pdf_task_manager import PDFTaskManager
task_status = task_manager.get_task_status(task_id, user_id)

# 修改后（Celery）
from celery_tasks import generate_pdf_task
task = generate_pdf_task.AsyncResult(task_id)
status = task.state  # 'PENDING', 'PROGRESS', 'SUCCESS', 'FAILURE'
```

---

## 总结

### 关系图

```
┌─────────────────────────────────────────────────────────┐
│                   用户请求流程                            │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  Flask API (tr_fill_in_api.py)                          │
│  - 接收请求                                              │
│  - 验证身份                                              │
│  - 创建任务                                              │
│  - 返回任务 ID                                           │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  任务存储                                                │
│  Threading: SQLite (pdf_tasks 表)                       │
│  Celery: Redis (任务队列)                                │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  任务执行                                                │
│  Threading: Flask 进程的后台线程                         │
│  Celery: Celery Worker 进程（独立）                      │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  结果存储                                                │
│  Threading: SQLite (pdf_tasks 表)                       │
│  Celery: Redis (任务结果)                                │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  前端轮询                                                │
│  GET /api/pdf/task-status/<task_id>                      │
│  Flask API 查询任务状态并返回                             │
└─────────────────────────────────────────────────────────┘
```

### 关键区别

| 方面 | Threading | Celery |
|------|-----------|--------|
| **进程** | 同一进程 | 独立进程 |
| **存储** | SQLite | Redis |
| **持久化** | ❌ 无 | ✅ 有 |
| **重试** | ❌ 无 | ✅ 有 |
| **监控** | ⭐ 基础 | ⭐⭐⭐⭐⭐ 专业 |

---

**当前状态：** 你的系统使用 Threading 方案，已实现异步 PDF 生成。如果需要更强大的功能，可以迁移到 Celery。

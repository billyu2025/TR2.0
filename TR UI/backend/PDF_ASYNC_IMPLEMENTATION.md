# PDF 异步生成实现说明

## 概述

PDF 生成已从同步模式改为异步模式，解决了后端拥堵问题。现在 PDF 生成不会阻塞 API 响应，多个用户可以同时生成 PDF。

## 实现细节

### 1. 新增文件

- `pdf_task_manager.py` - PDF 任务管理器，负责管理异步 PDF 生成任务

### 2. 数据库表

新增 `pdf_tasks` 表，用于存储 PDF 生成任务：

```sql
CREATE TABLE pdf_tasks (
    task_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    order_no INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    message TEXT,
    pdf_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    completed_at TEXT,
    expires_at TEXT
);
```

### 3. API 变更

#### 旧 API（已废弃，但仍保留兼容性）

```
POST /api/pdf/generate
```

**旧行为：** 同步生成 PDF，阻塞直到完成（10-60 秒）

#### 新 API（推荐使用）

```
POST /api/pdf/generate
```

**新行为：** 立即返回任务 ID，后台异步处理

**请求：**
```json
{
    "order_no": 123456
}
```

**响应（202 Accepted）：**
```json
{
    "success": true,
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "order_no": 123456,
    "message": "PDF 生成任务已创建，正在后台处理"
}
```

#### 查询任务状态

```
GET /api/pdf/task-status/<task_id>
```

**响应：**

**处理中：**
```json
{
    "success": true,
    "task_id": "...",
    "order_no": 123456,
    "status": "processing",
    "progress": 45,
    "message": "正在生成 PDF..."
}
```

**完成：**
```json
{
    "success": true,
    "task_id": "...",
    "order_no": 123456,
    "status": "completed",
    "progress": 100,
    "message": "PDF 生成完成",
    "pdf_path": "/path/to/pdf",
    "pdf_status": "generated"
}
```

**失败：**
```json
{
    "success": true,
    "task_id": "...",
    "order_no": 123456,
    "status": "failed",
    "progress": 0,
    "message": "PDF 生成失败: ...",
    "error_message": "...",
    "pdf_status": "failed"
}
```

## 前端集成指南

### 步骤 1：修改 PDF 生成调用

**旧代码（同步）：**
```javascript
// 旧代码 - 会阻塞
const response = await apiFetch('/api/pdf/generate', {
    method: 'POST',
    body: JSON.stringify({ order_no: orderNo })
});

if (response.success) {
    // PDF 已生成，可以下载
    showDownloadButton();
}
```

**新代码（异步）：**
```javascript
// 新代码 - 立即返回
const response = await apiFetch('/api/pdf/generate', {
    method: 'POST',
    body: JSON.stringify({ order_no: orderNo })
});

if (response.success) {
    const taskId = response.task_id;
    
    // 显示进度提示
    showProgressMessage('PDF 生成中，请稍候...');
    
    // 开始轮询任务状态
    pollTaskStatus(taskId, orderNo);
}
```

### 步骤 2：实现任务状态轮询

```javascript
async function pollTaskStatus(taskId, orderNo) {
    const maxAttempts = 120; // 最多轮询 2 分钟（每 1 秒一次）
    let attempts = 0;
    
    const poll = async () => {
        try {
            const response = await apiFetch(`/api/pdf/task-status/${taskId}`);
            
            if (response.status === 'completed') {
                // PDF 生成完成
                hideProgressMessage();
                showDownloadButton();
                updatePdfStatus(orderNo, 'generated');
                return;
            } else if (response.status === 'failed') {
                // PDF 生成失败
                hideProgressMessage();
                showErrorMessage(response.error_message || 'PDF 生成失败');
                updatePdfStatus(orderNo, 'failed');
                return;
            } else if (response.status === 'processing') {
                // 更新进度
                updateProgress(response.progress, response.message);
            }
            
            // 继续轮询
            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(poll, 1000); // 1 秒后再次查询
            } else {
                // 超时
                hideProgressMessage();
                showErrorMessage('PDF 生成超时，请稍后重试');
            }
        } catch (error) {
            console.error('查询任务状态失败:', error);
            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(poll, 2000); // 错误时 2 秒后重试
            } else {
                hideProgressMessage();
                showErrorMessage('查询任务状态失败');
            }
        }
    };
    
    // 立即开始第一次查询
    poll();
}
```

### 步骤 3：更新进度显示

```javascript
function updateProgress(progress, message) {
    // 更新进度条
    const progressBar = document.getElementById('pdf-progress-bar');
    if (progressBar) {
        progressBar.style.width = `${progress}%`;
        progressBar.setAttribute('aria-valuenow', progress);
    }
    
    // 更新消息
    const progressMessage = document.getElementById('pdf-progress-message');
    if (progressMessage) {
        progressMessage.textContent = message || `生成中... ${progress}%`;
    }
}
```

### 步骤 4：更新订单列表

PDF 生成完成后，需要刷新订单列表以显示新的 PDF 状态：

```javascript
function updatePdfStatus(orderNo, status) {
    // 更新本地状态
    const record = findRecordByOrderNo(orderNo);
    if (record) {
        record.pdf_status = status;
        // 触发 Vue 响应式更新
        // ...
    }
    
    // 或者重新加载订单列表
    // loadOrdersFromAPI();
}
```

## 任务状态说明

| 状态 | 说明 | 前端行为 |
|------|------|---------|
| `pending` | 任务已创建，等待处理 | 显示"等待处理..." |
| `processing` | 正在生成 PDF | 显示进度条和进度消息 |
| `completed` | PDF 生成完成 | 显示下载按钮 |
| `failed` | PDF 生成失败 | 显示错误消息 |

## 优势

1. **不阻塞 API**：PDF 生成不再阻塞其他请求
2. **更好的用户体验**：立即响应，显示进度
3. **支持并发**：多个用户可以同时生成 PDF
4. **任务跟踪**：可以查询任务状态和进度
5. **错误处理**：失败时提供详细错误信息

## 注意事项

1. **任务过期**：PDF 任务在 1 天后自动过期
2. **轮询频率**：建议每 1 秒轮询一次，避免过于频繁
3. **超时处理**：建议设置最大轮询时间（如 2 分钟）
4. **错误重试**：网络错误时可以重试，但不要无限重试

## 兼容性

旧的同步 API 仍然保留，但建议尽快迁移到新的异步 API。

## 测试

1. **测试正常流程**：
   - 创建 PDF 任务
   - 轮询任务状态
   - 等待完成
   - 验证 PDF 可以下载

2. **测试错误处理**：
   - 使用不存在的订单号
   - 验证错误消息正确显示

3. **测试并发**：
   - 同时生成多个 PDF
   - 验证不会互相阻塞

## 故障排除

### 问题 1：任务状态一直显示 "pending"

**可能原因：**
- 后台线程未启动
- 任务处理出错

**解决方法：**
- 检查后端日志
- 验证 `pdf_tasks` 表是否正确创建

### 问题 2：进度不更新

**可能原因：**
- 轮询频率过低
- 前端轮询逻辑错误

**解决方法：**
- 检查轮询间隔（建议 1 秒）
- 检查网络请求是否成功

### 问题 3：PDF 生成完成但无法下载

**可能原因：**
- PDF 文件路径错误
- 文件权限问题

**解决方法：**
- 检查 `pdf_path` 是否正确
- 验证文件是否存在
- 检查文件权限

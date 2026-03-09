# 下载稳定性改进方案

## 问题分析

使用内网访问 192.168.32.97:8000 时，TR 管理记录下载经常出现闪退，可能的原因：

### 1. Nginx 超时设置过短
- 当前设置：60秒
- 问题：大文件下载或处理时间较长时，会超时断开
- 影响：导致前端请求失败，页面闪退

### 2. 网络连接不稳定
- 内网访问可能存在延迟
- 连接中断时没有重试机制
- fetch 请求没有超时设置

### 3. 前端错误处理不完善
- 某些错误没有被正确捕获
- 错误信息不够详细，难以排查

### 4. 轮询任务状态时缺少超时
- 如果网络中断，轮询会一直等待
- 没有最大重试次数限制

## 改进方案

### 1. 增加 Nginx 超时时间

修改 `nginx-1.28.0/conf/nginx.conf`：

```nginx
# 超时设置（增加超时时间，适应大文件下载）
proxy_connect_timeout 300s;  # 从 60s 增加到 300s（5分钟）
proxy_send_timeout 300s;     # 从 60s 增加到 300s
proxy_read_timeout 300s;     # 从 60s 增加到 300s（关键：文件下载需要更长时间）
```

### 2. 添加前端请求超时和重试机制

在 `scripts/tr-records.js` 中添加：

```javascript
// 带超时的 fetch 包装函数
async function fetchWithTimeout(url, options = {}, timeout = 300000) { // 5分钟超时
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error('请求超时，请检查网络连接');
        }
        throw error;
    }
}

// 带重试的 fetch 包装函数
async function fetchWithRetry(url, options = {}, maxRetries = 3, retryDelay = 1000) {
    let lastError;
    for (let i = 0; i < maxRetries; i++) {
        try {
            return await fetchWithTimeout(url, options);
        } catch (error) {
            lastError = error;
            if (i < maxRetries - 1) {
                console.log(`请求失败，${retryDelay}ms 后重试 (${i + 1}/${maxRetries})...`);
                await new Promise(resolve => setTimeout(resolve, retryDelay));
                retryDelay *= 2; // 指数退避
            }
        }
    }
    throw lastError;
}
```

### 3. 改进轮询任务状态的错误处理

在 `pollTaskStatus` 方法中：

```javascript
async pollTaskStatus(taskId, zipFilename, total) {
    // ... 现有代码 ...
    
    // 添加网络错误检测
    const checkStatus = async () => {
        try {
            const response = await fetchWithRetry(
                buildApiUrl(`/api/download/task-status/${taskId}`),
                { headers, signal: this.currentAbortController.signal },
                300000, // 5分钟超时
                3,      // 最多重试3次
                2000    // 初始重试延迟2秒
            );
            // ... 处理响应 ...
        } catch (error) {
            // 改进错误处理
            if (error.name === 'AbortError' || this.isCancelling) {
                clearInterval(pollInterval);
                reject(new Error('下载已取消'));
                return;
            }
            
            // 网络错误：记录并重试
            console.error(`[轮询错误] 第 ${attempts} 次查询失败:`, error);
            
            if (attempts >= maxAttempts) {
                clearInterval(pollInterval);
                reject(new Error(`查询任务状态超时：${error.message || '网络连接失败'}`));
                return;
            }
            
            // 如果是网络错误，等待更长时间后重试
            if (error.message.includes('超时') || error.message.includes('网络')) {
                await new Promise(resolve => setTimeout(resolve, 5000)); // 等待5秒
            }
        }
    };
}
```

### 4. 添加全局错误处理

在页面加载时添加：

```javascript
// 全局错误处理
window.addEventListener('error', (event) => {
    console.error('全局错误:', event.error);
    // 如果是下载相关的错误，显示友好提示
    if (event.error && event.error.message && event.error.message.includes('下载')) {
        alert('下载过程中发生错误，请检查网络连接后重试');
    }
});

// 未处理的 Promise 拒绝
window.addEventListener('unhandledrejection', (event) => {
    console.error('未处理的 Promise 拒绝:', event.reason);
    if (event.reason && event.reason.message && event.reason.message.includes('下载')) {
        alert('下载过程中发生错误，请检查网络连接后重试');
    }
});
```

### 5. 改进下载文件的错误处理

在下载文件时添加更详细的错误信息：

```javascript
async downloadFile(taskId, zipFilename) {
    try {
        const response = await fetchWithRetry(
            buildApiUrl(`/api/download/download/${taskId}`),
            { headers, signal: this.currentAbortController.signal },
            600000, // 10分钟超时（大文件下载）
            3,      // 最多重试3次
            5000    // 初始重试延迟5秒
        );
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `下载失败: HTTP ${response.status}`);
        }
        
        // ... 处理下载 ...
    } catch (error) {
        // 详细错误信息
        let errorMsg = '下载失败';
        if (error.message.includes('超时')) {
            errorMsg = '下载超时，文件可能较大，请稍后重试';
        } else if (error.message.includes('网络')) {
            errorMsg = '网络连接失败，请检查网络后重试';
        } else {
            errorMsg = error.message || '下载时发生未知错误';
        }
        throw new Error(errorMsg);
    }
}
```

## 实施步骤

1. **立即修改 Nginx 配置**（最重要）
   - 增加超时时间到 300 秒
   - 重启 Nginx

2. **修改前端代码**
   - 添加 fetchWithTimeout 和 fetchWithRetry 函数
   - 改进 pollTaskStatus 的错误处理
   - 添加全局错误处理

3. **测试验证**
   - 在内网环境下测试下载功能
   - 检查是否还会出现闪退
   - 查看浏览器控制台的错误信息

## 监控和日志

建议添加：
- 前端错误日志记录
- 后端请求日志记录
- 下载任务状态监控

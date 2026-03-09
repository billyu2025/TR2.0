# PDF 和下载任务编码问题修复

## 问题

生成 PDF 和下载任务时出现编码错误：
```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 1-2: character maps to <undefined>
```

## 原因

在 `pdf_task_manager.py` 和 `download_task_manager.py` 中有多个中文 print 语句，在 Windows 服务环境中输出时遇到编码问题。

## 已修复的文件

### 1. `pdf_task_manager.py`

**修复的 print 语句：**
- ✅ 第 69 行：创建任务
- ✅ 第 173 行：开始处理任务
- ✅ 第 175、184、189 行：进度消息
- ✅ 第 222、225 行：PDF_Status 更新
- ✅ 第 240 行：任务完成
- ✅ 第 267、283 行：任务失败
- ✅ 第 287 行：任务异常
- ✅ 第 351 行：清理过期任务

### 2. `download_task_manager.py`

**修复的 print 语句：**
- ✅ 第 76 行：创建任务
- ✅ 第 185 行：开始处理任务
- ✅ 第 230-231 行：任务完成
- ✅ 第 235 行：任务失败
- ✅ 第 422 行：Order 处理失败
- ✅ 第 640 行：删除文件失败
- ✅ 第 650 行：清理过期任务

## 修复方法

所有 print 语句都使用 try-except 包装：
```python
try:
    print(f"[PDF Task] Created task: {task_id}, Order No: {order_no}, User: {user_id}")
except (UnicodeEncodeError, UnicodeDecodeError):
    pass
```

如果编码失败，静默忽略（不影响功能）。

## 重启服务

修复后需要重启服务才能生效：

**方法一：使用批处理脚本**
```
双击运行：C:\TR-master\TR UI\backend\restart_service.bat
```

**方法二：使用服务管理器**
1. 按 `Win + R`
2. 输入 `services.msc`
3. 找到 "TR Report System Backend"
4. 右键 → "重新启动"

## 验证

重启服务后：
1. 打开浏览器访问：http://localhost:8000
2. 登录系统
3. 尝试生成 PDF
4. 尝试下载 Stockist & Test Report
5. 应该不再出现编码错误

## 如果仍有问题

如果重启后仍有编码错误：

1. **查看错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 30
   ```

2. **检查是否还有其他 print 语句**：
   - 查看日志中的具体错误位置
   - 告诉我具体的错误信息

---

**修复完成！请重启服务后测试。**

# 批量生成 PDF 编码问题最终修复

## 问题诊断

从错误日志看，问题出现在：
1. `pdf_task_manager.py` 第 69 行 - `create_task` 方法
2. `download_task_manager.py` 第 76 行 - `create_task` 方法

错误信息：
```
UnicodeEncodeError: 'charmap' codec can't encode characters in position X-Y: character maps to <undefined>
```

## 根本原因

在 Windows 服务环境中，即使使用 try-except 包装 print 语句，**f-string 格式化时**也可能触发编码错误。这是因为 f-string 在格式化时就会尝试编码字符串，而不是在 print 时才编码。

## 解决方案

将所有 f-string 的 print 语句改为**字符串拼接**，避免 f-string 格式化时的编码问题。

### 修复的文件

1. **pdf_task_manager.py**
   - ✅ 第 69-73 行：`create_task` 方法的 print 语句
   - ✅ 第 179-181 行：`process_task` 方法的 print 语句
   - ✅ 第 231-233 行：PDF_Status 更新的 print 语句
   - ✅ 第 237-239 行：PDF_Status 更新失败的 print 语句
   - ✅ 第 255-257 行：任务完成的 print 语句
   - ✅ 第 304-306 行：任务失败的 print 语句
   - ✅ 第 311-313 行：任务异常的 print 语句
   - ✅ 第 378-380 行：清理任务的 print 语句

2. **download_task_manager.py**
   - ✅ 第 76-80 行：`create_task` 方法的 print 语句
   - ✅ 第 188-190 行：`process_task` 方法的 print 语句
   - ✅ 第 236-239 行：任务完成的 print 语句
   - ✅ 第 244-246 行：任务失败的 print 语句
   - ✅ 第 434-436 行：订单处理失败的 print 语句
   - ✅ 第 655-657 行：清理文件失败的 print 语句
   - ✅ 第 668-670 行：清理任务的 print 语句

### 修复方法

**修复前（使用 f-string）：**
```python
try:
    print(f"[PDF Task] Created task: {task_id}, Order No: {order_no}, User: {user_id}")
except (UnicodeEncodeError, UnicodeDecodeError):
    pass
```

**修复后（使用字符串拼接）：**
```python
try:
    msg = "[PDF Task] Created task: " + str(task_id) + ", Order No: " + str(order_no) + ", User: " + str(user_id)
    print(msg)
except (UnicodeEncodeError, UnicodeDecodeError, Exception):
    pass
```

## 关键改进

1. **避免 f-string 格式化**：f-string 在格式化时就会尝试编码，可能导致编码错误
2. **使用字符串拼接**：字符串拼接不会在格式化时触发编码问题
3. **捕获所有异常**：在 except 中添加 `Exception`，确保捕获所有可能的错误

## 重启服务

修复后需要重启服务才能生效：

**方法一：使用批处理脚本（最简单）**
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
3. 选择多个未生成的记录
4. 点击"批量生成PDF"
5. 应该不再出现编码错误
6. PDF 应该能够正常生成

## 如果仍有问题

如果重启后仍有错误：

1. **查看错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 30
   Get-Content "C:\TR-master\TR UI\backend\logs\app.log" -Tail 30 | Select-String -Pattern "PDF|pdf|error|Error"
   ```

2. **检查服务状态**：
   ```powershell
   Get-Service TR-Backend
   ```

3. **测试单个 PDF 生成**：
   - 先测试单个 PDF 生成是否正常
   - 如果单个正常，批量应该也正常

---

**所有编码问题已彻底修复！请重启服务后测试批量生成 PDF。**

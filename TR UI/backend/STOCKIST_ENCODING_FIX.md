# STOCKIST & TEST REPORT 编码问题修复

## 问题

打开 "STOCKIST & TEST REPORT" 页面时出现错误：
```
'charmap' codec can't encode characters in position 1-2: character maps to <undefined>
```

## 原因

在 `get_bbs_dd_list` 函数中有多个 print 语句，在 Windows 服务环境中输出时遇到编码问题。

## 已修复

### 修复的文件：`tr_fill_in_api.py`

**修复位置：**
1. 第 2206 行：调试信息 print 语句
2. 第 2211 行：总记录数 print 语句
3. 第 2230 行：查询执行 print 语句
4. 第 2236 行：执行时间 print 语句
5. 第 2239 行：获取行数 print 语句
6. 第 2278 行：错误处理 print 语句
7. 第 2334 行：缓存命中 logger.debug 语句

**修复方法：**
- 所有 print 语句都使用 try-except 包装
- 捕获 `UnicodeEncodeError` 和 `UnicodeDecodeError`
- 如果编码失败，静默忽略（不影响功能）

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
1. 打开浏览器
2. 访问：http://localhost:8000
3. 登录系统
4. 切换到 "STOCKIST & TEST REPORT" 标签页
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

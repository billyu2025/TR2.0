# 分页功能调试指南

## 问题描述
Stockist & Test Report 页面无法翻页

## 已实施的修复

### 1. 添加调试日志
在以下关键位置添加了 console.log：
- `loadOrdersFromAPI()` - 记录 API 调用参数和返回结果
- `nextPage()` - 记录翻页操作
- `prevPage()` - 记录翻页操作

### 2. 修复搜索参数传递
**问题：** 在正常分页时，即使没有搜索条件，也会传递空的搜索参数，可能导致后端误判。

**修复：** 只有在 `isSearching = true` 时才传递搜索参数。

### 3. 增强错误处理
添加了对 API 返回结果的验证，确保包含分页信息。

## 调试步骤

### 步骤 1：打开浏览器控制台
1. 按 F12 打开开发者工具
2. 切换到 Console 标签页

### 步骤 2：切换到 Stockist & Test Report 标签页
观察控制台输出，应该看到：
```
[分页] loadOrdersFromAPI 被调用 { page: 1, activeSubTab: 'stocklist-test', ... }
[分页] API 请求参数: page=1&per_page=10&tab=stocklist-test
[分页] API返回的分页信息: { current_page: 1, total_pages: X, ... }
```

### 步骤 3：检查分页信息
查看控制台中的 `total_pages` 值：
- 如果 `total_pages = 1`，说明只有一页数据，无法翻页（这是正常的）
- 如果 `total_pages > 1`，但按钮被禁用，可能是前端逻辑问题

### 步骤 4：测试翻页
1. 点击"下一页"按钮
2. 观察控制台输出：
   ```
   [分页] nextPage 被调用 { currentPage: 1, totalPages: X, ... }
   [分页] 加载下一页: 2
   [分页] loadOrdersFromAPI 被调用 { page: 2, ... }
   ```

### 步骤 5：检查按钮状态
在控制台输入以下命令检查状态：
```javascript
// 检查当前分页状态
console.log({
    currentPage: app.currentPage,
    totalPages: app.totalPages,
    totalPagesComputed: app.totalPagesComputed,
    activeSubTab: app.activeSubTab,
    isSearching: app.isSearching
});
```

## 可能的问题和解决方案

### 问题 1：totalPages 始终为 1
**原因：** 
- 数据确实只有一页
- 后端分页计算错误
- API 返回的分页信息不正确

**检查：**
1. 查看控制台中的 `total_records` 值
2. 如果 `total_records > 10`（假设每页10条），但 `total_pages = 1`，说明后端计算有问题

**解决：** 检查后端 `get_bbs_dd_list` 函数的分页计算逻辑

### 问题 2：按钮被禁用
**原因：**
- `currentPage === 1` 时，"上一页"按钮被禁用（正常）
- `currentPage === totalPages` 时，"下一页"按钮被禁用（正常）
- `totalPages` 计算错误

**检查：**
```javascript
// 在控制台检查
app.totalPages  // 应该返回总页数
app.currentPage  // 应该返回当前页
```

### 问题 3：点击按钮没有反应
**原因：**
- 事件绑定问题
- Vue 响应式更新问题

**检查：**
1. 点击按钮时，控制台应该输出 `[分页] nextPage 被调用` 或 `[分页] prevPage 被调用`
2. 如果没有输出，说明事件没有绑定

**解决：** 检查 HTML 中的 `@click` 绑定

### 问题 4：API 返回错误
**检查：**
1. 查看 Network 标签页
2. 找到 `/api/orders/list` 请求
3. 查看响应内容，确认是否包含 `pagination` 字段

## 测试用例

### 测试 1：基本分页
1. 切换到 Stockist & Test Report 标签页
2. 确认分页按钮显示
3. 点击"下一页"
4. 验证数据是否更新

### 测试 2：边界情况
1. 在第一页时，点击"上一页"（应该被禁用）
2. 在最后一页时，点击"下一页"（应该被禁用）

### 测试 3：标签页切换
1. 在 TR记录管理标签页翻到第3页
2. 切换到 Stockist & Test Report 标签页
3. 验证是否重置到第1页

## 下一步

如果问题仍然存在，请：
1. 复制控制台中的所有 `[分页]` 相关日志
2. 检查 Network 标签页中的 API 响应
3. 提供具体的错误信息

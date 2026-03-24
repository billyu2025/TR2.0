# SQL 占位符修复总结

## 问题
在切换到 PostgreSQL 后，代码中使用了硬编码的 `?` 占位符（SQLite 格式），但 PostgreSQL 需要使用 `%s` 占位符。这导致了 `psycopg.ProgrammingError: the query has 0 placeholders but 1 parameters were passed` 错误。

## 修复内容

已修复以下函数中的硬编码占位符：

1. **`_get_session(token)`** (第 990 行)
   - 修复前: `"SELECT token, user_id, expires_at FROM user_sessions WHERE token = ?"`
   - 修复后: `f"SELECT token, user_id, expires_at FROM user_sessions WHERE token = {db_placeholders(1)}"`

2. **`_fetch_user(conn, *, username=None, user_id=None)`** (第 929, 931 行)
   - 修复了 username 和 user_id 查询

3. **`_fetch_user_job_nos(conn, user_id)`** (第 938 行)
   - 修复了 user_id 查询

4. **`_replace_user_job_nos(conn, user_id, job_nos)`** (第 946, 949 行)
   - 修复了 DELETE 和 INSERT 语句
   - 添加了 PostgreSQL 兼容的 `ON CONFLICT DO NOTHING` 语法

5. **`_create_session(user_id)`** (第 961, 963-967 行)
   - 修复了 DELETE 和 INSERT 语句

6. **`_delete_session(token)`** (第 979 行)
   - 修复了 DELETE 语句

7. **`_get_session(token)` 中的过期清理** (第 1026 行)
   - 修复了过期会话的 DELETE 语句

8. **用户管理相关函数** (第 1727, 1900, 1905 行)
   - 修复了用户查询和删除操作

## 使用的修复方法

所有修复都使用了 `db_placeholders(count)` 函数，该函数会根据数据库类型返回正确的占位符：
- PostgreSQL: `%s`
- SQLite: `?`

## 验证

修复后，所有关键的用户认证和会话管理函数都应该能在 PostgreSQL 和 SQLite 上正常工作。

## 注意事项

代码中可能还有其他地方使用了硬编码的 `?` 占位符，特别是在：
- 订单查询相关函数
- PDF 生成相关函数
- 文件索引相关函数

这些函数在需要时也应该进行类似的修复。

-- 检查3年数据库中的用户表
-- 使用方法: sqlite3 data_3years.db < check_user_tables.sql

-- 1. 列出所有表
SELECT '=== All Tables ===' AS info;
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;

-- 2. 检查用户相关表
SELECT '=== User Tables ===' AS info;
SELECT name FROM sqlite_master 
WHERE type='table' AND name LIKE 'user%' 
ORDER BY name;

-- 3. 查看user_accounts表结构
SELECT '=== user_accounts Structure ===' AS info;
SELECT sql FROM sqlite_master 
WHERE type='table' AND name='user_accounts';

-- 4. 查看user_accounts数据
SELECT '=== user_accounts Data ===' AS info;
SELECT id, username, role, is_active, created_at 
FROM user_accounts;

-- 5. 查看user_job_access数据
SELECT '=== user_job_access Data ===' AS info;
SELECT * FROM user_job_access;

-- 6. 查看user_sessions数据
SELECT '=== user_sessions Data ===' AS info;
SELECT * FROM user_sessions;


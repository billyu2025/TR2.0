# 密码有效期功能说明

## 功能概述

为普通账户（user 和 manager）实现密码有效期管理功能，帮助客户保护密码隐私。

## 主要功能

### 1. 密码有效期设置
- **有效期**：普通账户密码有效期为 **180 天**
- **适用范围**：仅适用于 `user` 和 `manager` 角色
- **管理员账户**：`admin` 账户密码永不过期

### 2. 数据库字段
在 `user_accounts` 表中新增两个字段：
- `password_changed_at`：密码最后修改时间（ISO 格式）
- `password_expires_at`：密码过期时间（ISO 格式，180 天后）

### 3. 密码剩余天数显示
- 在用户列表 API 中显示每个用户的密码剩余天数
- 在用户详情 API 中显示密码剩余天数
- 如果密码已过期，显示负数（如 -5 表示已过期 5 天）
- 如果密码永不过期（admin），显示 `null`

### 4. 自动生成强密码
- **密码长度**：10 位
- **字符类型**：包含大小写字母、数字、特殊符号
- **特殊符号**：`!@#$%^&*`
- **安全性**：使用 `secrets` 模块生成密码，确保随机性

### 5. 密码重置功能
- **API 端点**：`POST /api/admin/users/<username>/reset-password`
- **功能**：管理员可以为用户重置密码
- **流程**：
  1. 自动生成 10 位强密码
  2. 更新用户密码
  3. 重置密码过期时间（180 天后）
  4. 返回新生成的密码（仅此一次，用于显示给管理员）

## API 变更

### 1. 创建用户 API
**端点**：`POST /api/admin/users`

**新增返回字段**：
```json
{
  "success": true,
  "user": {
    "username": "user1",
    "password_days_remaining": 180,
    "password_expires_at": "2026-07-26T10:00:00"
  }
}
```

### 2. 更新用户 API
**端点**：`PUT /api/admin/users/<username>`

**行为变更**：
- 当更新密码时，自动重置密码过期时间（180 天后）
- 返回数据中包含 `password_days_remaining` 和 `password_expires_at`

### 3. 用户列表 API
**端点**：`GET /api/admin/users`

**新增返回字段**：
```json
{
  "success": true,
  "users": [
    {
      "username": "user1",
      "password_days_remaining": 150,
      "password_expires_at": "2026-07-26T10:00:00"
    }
  ]
}
```

### 4. 密码重置 API（新增）
**端点**：`POST /api/admin/users/<username>/reset-password`

**请求**：
- 需要管理员权限
- 无需请求体

**响应**：
```json
{
  "success": true,
  "new_password": "aB3$kL9mN2",
  "message": "Password has been reset for user user1. New password: aB3$kL9mN2"
}
```

## 代码实现

### 1. 新增函数

#### `_generate_random_password(length=10)`
生成随机强密码（大小写字母+数字+特殊符号）

#### `_calculate_password_days_remaining(password_expires_at)`
计算密码剩余天数

### 2. 配置常量
```python
PASSWORD_EXPIRY_DAYS = 180  # 普通账户密码有效期（天）
```

### 3. 数据库迁移
- 自动检测并添加 `password_changed_at` 和 `password_expires_at` 字段
- 兼容现有数据库，无需手动迁移

## 使用示例

### 创建用户
```python
POST /api/admin/users
{
  "username": "user1",
  "password": "initial_password",
  "role": "user"
}
```

响应中包含密码剩余天数：`password_days_remaining: 180`

### 重置密码
```python
POST /api/admin/users/user1/reset-password
```

响应中包含新生成的密码：`new_password: "aB3$kL9mN2"`

### 查看用户列表
```python
GET /api/admin/users
```

响应中每个用户都包含 `password_days_remaining` 字段，显示密码剩余天数。

## 安全考虑

1. **密码生成**：使用 `secrets` 模块，确保密码的随机性和安全性
2. **密码存储**：密码始终以哈希形式存储，不会明文保存
3. **密码重置**：新生成的密码仅在 API 响应中返回一次，建议管理员立即告知用户
4. **过期管理**：密码过期后，用户仍可登录，但系统会显示过期提醒（可在前端实现）

## 前端集成建议

1. **用户列表页面**：
   - 显示密码剩余天数
   - 如果剩余天数少于 30 天，显示警告颜色
   - 如果密码已过期，显示红色警告

2. **密码重置功能**：
   - 添加"重置密码"按钮
   - 点击后调用 API，显示新生成的密码
   - 建议使用模态框显示新密码，并提示用户立即修改

3. **密码过期提醒**：
   - 在用户登录时检查密码剩余天数
   - 如果少于 30 天，显示提醒消息
   - 如果已过期，显示警告消息

## 注意事项

1. **管理员账户**：`admin` 账户密码永不过期，不受此功能影响
2. **现有用户**：对于已存在的用户，如果 `password_expires_at` 为 `null`，系统会显示 `null`，表示密码未设置过期时间
3. **密码重置**：每次重置密码后，过期时间会重新计算（180 天后）
4. **时区处理**：密码过期时间使用本地时间（ISO 格式），计算剩余天数时使用系统当前时间

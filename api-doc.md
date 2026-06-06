# aikey.aixifs.com API 调用说明

> API 基础地址：**https://aikey.aixifs.com**

## 认证方式

### Admin 认证（管理接口）

```
Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY
New-Api-User: 1
```

### 用户认证（需登录）

Session Cookie 方式，先调 login 获取 cookie，后续请求携带 cookie。

---

## 一、用户管理（Admin）

### 创建用户

```
POST /api/user/
Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY
New-Api-User: 1
Content-Type: application/json

{
    "username": "user_abc123",
    "password": "xxx",
    "display_name": "用户昵称",
    "role": 1
}
```

返回：
```json
{"success": true, "message": ""}
```

注册后自动生成默认 API Key（无限额度 500000）。

### 查询用户

```
GET /api/user/{id}
Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY
New-Api-User: 1
```

返回：
```json
{
    "success": true,
    "data": {
        "id": 2,
        "username": "user_abc123",
        "display_name": "用户昵称",
        "role": 1,
        "status": 1,
        "group": "default",
        "quota": 500000,
        "used_quota": 0,
        "request_count": 0
    }
}
```

### 更新用户（含配额）

```
PUT /api/user/
Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY
New-Api-User: 1
Content-Type: application/json

{
    "id": 2,
    "quota": 600000
}
```

返回：
```json
{"success": true, "message": ""}
```

### 搜索用户

```
GET /api/user/search?keyword=xxx&group=default
Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY
New-Api-User: 1
```

### 删除用户

```
DELETE /api/user/{id}
Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY
New-Api-User: 1
```

---

## 二、用户认证（公开 / 用户）

### 注册（公开）

```
POST /api/user/register
Content-Type: application/json

{
    "username": "testuser",
    "password": "test123",
    "display_name": "测试用户"
}
```

注意：可能需要 Turnstile 验证，取决于服务端配置。

### 登录

```
POST /api/user/login
Content-Type: application/json

{
    "username": "testuser",
    "password": "test123"
}
```

返回：
```json
{
    "success": true,
    "data": {
        "id": 2,
        "username": "testuser",
        "display_name": "测试用户",
        "role": 1,
        "status": 1,
        "group": "default"
    }
}
```

响应 Set-Cookie 包含 session，后续 UserAuth 请求需携带。

### 获取当前用户信息

```
GET /api/user/self
Cookie: session=xxx
```

返回：
```json
{
    "success": true,
    "data": {
        "id": 2,
        "username": "testuser",
        "quota": 500000,
        "used_quota": 0,
        "request_count": 0,
        "group": "default",
        "aff_code": "xxxx"
    }
}
```

### 生成 Access Token

```
GET /api/user/token
Cookie: session=xxx
```

返回：
```json
{
    "success": true,
    "data": "sk-xxxxxxxx"
}
```

此 token 可用于 API 调用的 Bearer 认证。

---

## 三、API Key / Token 管理（用户）

所有接口需 session cookie。

### 列出所有 Token

```
GET /api/token/
Cookie: session=xxx
```

返回：
```json
{
    "success": true,
    "data": [
        {
            "id": 1,
            "name": "user_abc123的初始令牌",
            "key": "sk-xxx...",
            "remain_quota": 500000,
            "used_quota": 0,
            "unlimited_quota": true,
            "status": 1,
            "created_time": 1700000000
        }
    ]
}
```

### 创建 Token

```
POST /api/token/
Cookie: session=xxx
Content-Type: application/json

{
    "name": "我的Key",
    "remain_quota": 100000,
    "unlimited_quota": false,
    "expired_time": -1
}
```

返回：
```json
{"success": true, "data": {"id": 2, "key": "sk-xxx..."}}
```

### 获取 Token 详情

```
GET /api/token/{id}
Cookie: session=xxx
```

### 获取 Token Key（需额外验证）

```
POST /api/token/{id}/key
Cookie: session=xxx
```

### 删除 Token

```
DELETE /api/token/{id}
Cookie: session=xxx
```

---

## 四、兑换码 / 充值（Admin）

### 创建兑换码

```
POST /api/redemption/
Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY
New-Api-User: 1
Content-Type: application/json

{
    "name": "测试充值码",
    "quota": 50000,
    "count": 10,
    "expired_time": 0
}
```

返回：
```json
{"success": true, "data": ["CODE1", "CODE2", ...]}
```

### 用户兑换

```
POST /api/user/topup
Cookie: session=xxx
Content-Type: application/json

{
    "key": "CODE1"
}
```

返回：
```json
{"success": true, "data": 50000}
```

---

## 五、配额 / 用量查询

### 用户自查询

```
GET /api/user/self
Cookie: session=xxx
→ data.quota + data.used_quota
```

### Admin 查询任意用户

```
GET /api/user/{id}
Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY
New-Api-User: 1
→ data.quota + data.used_quota
```

---

## 总结：epay-go 调用的关键流程

```
1. Admin POST /api/user/          → 创建 new-api 用户
2. Admin GET  /api/user/:id       → 查询配额
3. Admin PUT  /api/user/          → 更新配额（加配额）
4. User  POST /api/user/login     → 获取 session cookie
5. User  GET  /api/token/         → 列出 API Keys
6. User  POST /api/token/         → 创建 API Key
7. User  DELETE /api/token/:id    → 删除 API Key
```

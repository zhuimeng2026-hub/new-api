# New-API 渠道添加方法

## 认证信息

从本地数据库获取管理员认证信息：

| 字段 | 值 |
|------|-----|
| access_token | `JDlAGRIXSAKHSBMkXrct5NNaJ6fY` |
| New-Api-User header | `1` |
| API 基础地址 | `https://aikey.aixifs.com/` |

## 查询现有渠道

```bash
curl https://aikey.aixifs.com/api/channel/ \n  -H "Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY" \n  -H "New-Api-User: 1" \n  -H "Content-Type: application/json"
```

## 添加新渠道

### 请求格式

```bash
curl -X POST https://aikey.aixifs.com/api/channel/ \n  -H "Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY" \n  -H "New-Api-User: 1" \n  -H "Content-Type: application/json" \n  -d '{
    "name": "渠道名称",
    "type": 1,
    "key": "sk-xxx",
    "base_url": "https://api.example.com/v1",
    "models": ["model1", "model2"],
    "status": 1
  }'
```

### 参数说明

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 渠道名称 |
| type | int | 提供商类型（见下方类型表） |
| key | string | API密钥 |
| base_url | string | API基础URL（非必填，有默认值） |
| models | array | 支持的模型列表 |
| status | int | 状态：1=启用，0=禁用 |
| priority | int | 优先级（数字越大优先级越高） |
| weight | int | 权重（用于负载均衡） |
| group | string | 分组，默认为"default" |

### 提供商类型（type）

| 值 | 提供商 |
|----|--------|
| 1 | OpenAI |
| 2 | Gemini |
| 3 | Claude |
| 8 | Midjourney Proxy |
| 14 | 智谱GLM |
| 15 | 360 |
| 17 | 通义千问 |
| 18 | 百度文心 |
| 19 | 模型服务 |
| 22 | Anthropic Claude |
| 23 | Vertex AI |
| 26 | 智谱BigModel |
| 35 | MiniMax |
| ... | 更多类型参考 constant/channel.go |

### 示例：添加OpenAI渠道

```bash
curl -X POST https://aikey.aixifs.com/api/channel/ \n  -H "Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY" \n  -H "New-Api-User: 1" \n  -H "Content-Type: application/json" \n  -d '{
    "name": "OpenAI官方",
    "type": 1,
    "key": "sk-proj-xxxxxxxx",
    "base_url": "https://api.openai.com/v1",
    "models": ["gpt-4o", "gpt-4o-mini", "o1-mini"],
    "status": 1,
    "priority": 100,
    "weight": 100
  }'
```

### 示例：添加通义千问渠道

```bash
curl -X POST https://aikey.aixifs.com/api/channel/ \n  -H "Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY" \n  -H "New-Api-User: 1" \n  -H "Content-Type: application/json" \n  -d '{
    "name": "通义千问",
    "type": 17,
    "key": "sk-xxxxxxxx",
    "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
    "status": 1,
    "priority": 50
  }'
```

## 测试渠道

```bash
curl -X POST https://aikey.aixifs.com/api/channel/test \n  -H "Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY" \n  -H "New-Api-User: 1" \n  -H "Content-Type: application/json" \n  -d '{
    "id": 渠道ID,
    "base_url": "https://api.example.com/v1",
    "key": "sk-xxx",
    "models": "model_name"
  }'
```

## 更新渠道

```bash
curl -X PUT https://aikey.aixifs.com/api/channel/{渠道ID} \n  -H "Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY" \n  -H "New-Api-User: 1" \n  -H "Content-Type: application/json" \n  -d '{
    "name": "新名称",
    "key": "sk-new-key",
    "status": 1
  }'
```

## 删除渠道

```bash
curl -X DELETE https://aikey.aixifs.com/api/channel/{渠道ID} \n  -H "Authorization: Bearer JDlAGRIXSAKHSBMkXrct5NNaJ6fY" \n  -H "New-Api-User: 1"
```

## 当前现有渠道

| ID | 名称 | 类型 | 状态 |
|----|------|------|------|
| 1 | 智谱BigModel | 26 | 禁用 |
| 2 | 智谱GLM-5(Anthropic) | 14 | 启用 |
| 3 | MiniMax | 35 | 禁用 |
| 4 | 通义千问(Qwen) | 17 | 启用 |
| 5 | 智谱GLM(Coding) | 14 | 启用 |
| 6 | 火山引擎(Coding) | 1 | 启用 |
| 7 | SCNET-MiniMax | 1 | 启用 |
# New-API 渠道添加方法

## 认证信息

从 `.env` 文件获取管理员认证信息：

| 字段 | 环境变量 | 说明 |
|------|----------|------|
| API 基础地址 | `new_admin_url` | 如 `https://aikey.aixifs.com/api` |
| access_token | `new_admin_key` | Bearer Token |
| New-Api-User | `New-Api-User` | 管理员用户 ID，默认 `1` |

## 查询现有渠道

```bash
curl -s "https://aikey.aixifs.com/api/channel/?page_size=50" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "New-Api-User: $ADMIN_USER"
```

## 添加新渠道

### 端点

```
POST /api/channel/
```

### 请求格式

请求体为 JSON，渠道字段必须嵌套在 `"channel"` 对象内：

```json
{
  "mode": "single",
  "channel": {
    "type": 1,
    "key": "sk-xxx",
    "name": "渠道名称",
    "models": "model1,model2"
  }
}
```

### 顶层参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mode | string | 是 | 添加模式：`"single"` 单 key、`"batch"` 批量（按换行分割 key，每个创建一个渠道）、`"multi_to_single"` 多 key 合并为一个渠道（轮询） |
| multi_key_mode | string | 否 | 多 key 选择策略，仅 `mode="multi_to_single"` 时生效 |
| batch_add_set_key_prefix_2_name | bool | 否 | 批量模式下，将 key 前 8 位追加到渠道名 |
| channel | object | 是 | 渠道对象，见下方 |

### channel 对象参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| type | int | **是** | 0 | 提供商类型（见下方类型表） |
| key | string | **是** | — | API Key，多个用 `\n` 分隔 |
| name | string | 推荐 | "" | 渠道名称 |
| models | string | 推荐 | "" | 支持的模型列表，逗号分隔（如 `"gpt-4o,gpt-4o-mini"`） |
| base_url | string | 否 | 按 type 自动填充 | 自定义上游 API 地址 |
| priority | int64 | 否 | 0 | 优先级，数字越大越优先 |
| weight | uint | 否 | 0 | 权重，同优先级时用于负载均衡 |
| status | int | 否 | 1 | 状态：`1`=启用，`2`=禁用 |
| group | string | 否 | "default" | 分组，逗号分隔多个分组 |
| model_mapping | string | 否 | null | 模型映射 JSON 字符串，如 `{"gpt-4":"qwen-max"}` |
| auto_ban | int | 否 | 1 | 自动禁用：`1`=启用，`=0` 关闭 |
| tag | string | 否 | null | 标签 |
| setting | string | 否 | null | 渠道额外设置 JSON |
| param_override | string | 否 | null | 请求参数覆盖 JSON |
| header_override | string | 否 | null | 请求头覆盖 JSON |
| remark | string | 否 | null | 备注（最多 255 字符） |
| other | string | 否 | "" | 其他配置（VertexAI 部署地区等） |
| openai_organization | string | 否 | null | OpenAI Organization ID |
| test_model | string | 否 | null | 测试用模型名 |
| status_code_mapping | string | 否 | "" | 状态码映射 |

### 校验规则

1. **添加时**：`channel` 对象不能为 null，`key` 不能为空
2. **模型名长度**：每个模型名不超过 255 字符
3. **VertexAI（type=41）**：`other` 字段必须为 JSON 且包含 `"default"` 部署地区，如 `{"default": "us-central1"}`
4. **Codex（type=57）**：`key` 必须为包含 `access_token` 和 `account_id` 的 JSON 对象

### 示例：添加 OpenAI 渠道

```bash
curl -X POST "https://aikey.aixifs.com/api/channel/" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "New-Api-User: $ADMIN_USER" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "single",
    "channel": {
      "name": "OpenAI官方",
      "type": 1,
      "key": "sk-proj-xxxxxxxx",
      "models": "gpt-4o,gpt-4o-mini,o1-mini",
      "priority": 100,
      "weight": 100
    }
  }'
```

### 示例：添加通义千问渠道

```bash
curl -X POST "https://aikey.aixifs.com/api/channel/" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "New-Api-User: $ADMIN_USER" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "single",
    "channel": {
      "name": "通义千问",
      "type": 17,
      "key": "sk-xxxxxxxx",
      "models": "qwen-plus,qwen-max,qwen-turbo",
      "priority": 50
    }
  }'
```

### 示例：批量添加（多 key 轮询）

```bash
curl -X POST "https://aikey.aixifs.com/api/channel/" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "New-Api-User: $ADMIN_USER" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "multi_to_single",
    "channel": {
      "name": "DeepSeek-多Key",
      "type": 43,
      "key": "sk-key1\nsk-key2\nsk-key3",
      "models": "deepseek-chat,deepseek-reasoner",
      "priority": 100
    }
  }'
```

### 示例：带模型映射

```bash
curl -X POST "https://aikey.aixifs.com/api/channel/" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "New-Api-User: $ADMIN_USER" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "single",
    "channel": {
      "name": "Qwen兼容OpenAI",
      "type": 17,
      "key": "sk-xxxxxxxx",
      "models": "qwen-max,qwen-plus",
      "model_mapping": "{\"gpt-4\":\"qwen-max\",\"gpt-3.5-turbo\":\"qwen-plus\"}",
      "priority": 100
    }
  }'
```

## 测试渠道

```bash
curl -X POST "https://aikey.aixifs.com/api/channel/test" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "New-Api-User: $ADMIN_USER" \
  -H "Content-Type: application/json" \
  -d '{
    "id": 渠道ID,
    "base_url": "https://api.example.com/v1",
    "key": "sk-xxx",
    "models": "model_name"
  }'
```

## 更新渠道

```bash
curl -X PUT "https://aikey.aixifs.com/api/channel/{渠道ID}" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "New-Api-User: $ADMIN_USER" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "新名称",
    "key": "sk-new-key",
    "status": 1
  }'
```

## 删除渠道

```bash
curl -X DELETE "https://aikey.aixifs.com/api/channel/{渠道ID}" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "New-Api-User: $ADMIN_USER"
```

## 渠道类型（type）

| 值 | 提供商 | 默认 Base URL |
|----|--------|---------------|
| 0 | Unknown | — |
| 1 | OpenAI | `https://api.openai.com` |
| 2 | Midjourney | `https://oa.api2d.net` |
| 3 | Azure | — |
| 4 | Ollama | `http://localhost:11434` |
| 5 | MidjourneyPlus | `https://api.openai-sb.com` |
| 6 | OpenAIMax | `https://api.openaimax.com` |
| 7 | OhMyGPT | `https://api.ohmygpt.com` |
| 8 | Custom | — |
| 9 | AILS | `https://api.caipacity.com` |
| 10 | AIProxy | `https://api.aiproxy.io` |
| 14 | Anthropic | `https://api.anthropic.com` |
| 15 | Baidu | `https://aip.baidubce.com` |
| 16 | Zhipu | `https://open.bigmodel.cn` |
| 17 | Ali (通义千问) | `https://dashscope.aliyuncs.com` |
| 18 | Xunfei | — |
| 19 | 360 | `https://api.360.cn` |
| 20 | OpenRouter | `https://openrouter.ai/api` |
| 24 | Gemini | `https://generativelanguage.googleapis.com` |
| 25 | Moonshot | `https://api.moonshot.cn` |
| 26 | Zhipu v4 | `https://open.bigmodel.cn` |
| 27 | Perplexity | `https://api.perplexity.ai` |
| 33 | AWS Bedrock | — |
| 34 | Cohere | `https://api.cohere.ai` |
| 35 | MiniMax | `https://api.minimax.chat` |
| 38 | Jina | — |
| 39 | Cloudflare | — |
| 40 | SiliconFlow | `https://api.siliconflow.cn` |
| 41 | Vertex AI | —（需 `other` 指定地区） |
| 42 | Mistral | `https://api.mistral.ai` |
| 43 | DeepSeek | `https://api.deepseek.com` |
| 45 | 火山引擎 | `https://ark.cn-beijing.volces.com` |
| 48 | xAI | `https://api.x.ai` |
| 50 | Kling (可灵) | — |
| 51 | 即梦 Jimeng | — |
| 52 | Vidu | — |
| 57 | Codex | `https://chatgpt.com` |
| 58 | 小米 MiMo | — |
| 59 | ModelScope | — |

完整列表见 `constant/channel.go`。

## 渠道额外设置（setting 字段）

JSON 格式，可选字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| force_format | bool | 强制消息格式 |
| thinking_to_content | bool | 将 thinking token 转为 content |
| proxy | string | 上游代理地址 |
| pass_through_body_enabled | bool | 启用 body 透传 |
| system_prompt | string | 自定义 system prompt |
| system_override | bool | 是否覆盖 system prompt |

## 渠道其他设置（settings 字段）

JSON 格式，存储在数据库 `settings` 列：

| 字段 | 类型 | 说明 |
|------|------|------|
| azure_responses_version | string | Azure API 版本 |
| vertex_key_type | string | Vertex AI key 类型：`"json"` 或 `"api_key"` |
| openrouter_enterprise | bool | OpenRouter 企业模式 |
| claude_beta_query | bool | Claude 请求附加 `?beta=true` |
| aws_key_type | string | AWS key 类型：`"ak_sk"` 或 `"api_key"` |

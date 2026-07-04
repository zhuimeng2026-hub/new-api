# new-api 渠道管理脚本使用指南

## 概述

四个专用渠道管理脚本，每个脚本管理一种渠道类型，支持五个子命令：

| 命令 | 说明 | 示例 |
|------|------|------|
| `test` | 测试连通性（**默认**） | `python3 channel_glm.py` |
| `list` | 查询渠道列表 | `python3 channel_glm.py list` |
| `add` | 添加渠道 | `python3 channel_glm.py add` |
| `update` | 修改渠道 | `python3 channel_glm.py update 33 --priority 100` |
| `delete` | 删除渠道 | `python3 channel_glm.py delete 33` |

## 脚本列表

| 脚本 | 渠道类型 | type | 默认模型 |
|------|----------|------|----------|
| `channel_glm.py` | GLM（Anthropic 格式） | 14 | glm-5, glm-5-turbo, glm-5.1, glm-5.2 |
| `channel_codex.py` | Codex（OpenAI 格式） | 1 | gpt-3.5-turbo, gpt-4o-mini, gpt-5, gpt-5.4, gpt-5.4-mini, gpt-5.5 |
| `channel_claude.py` | Claude（Anthropic 格式） | 14 | claude-fable-5, claude-haiku-4-5, claude-opus-4-5/4-6/4-7/4-8, claude-sonnet-4-5/4-6, claude-sonnet-5 |
| `channel_images.py` | Images（OpenAI 格式） | 1 | gpt-image-2 |

## 凭据来源

脚本读取两个 `.env` 文件（后者覆盖前者）：

| 文件 | 提供内容 |
|------|----------|
| `/opt/new-api/.env` | `new_admin_url`, `new_admin_key`, `New-Api-User`（管理员认证） |
| `scripts/.env` | `base_url`, `glm_key`, `codex_key`, `claude_key`, `images_key` 等（渠道上游地址和 Key） |

### 关键参数：base_url

`base_url` 是上游 API 地址，**必须在 `scripts/.env` 中配置**，否则会使用渠道类型的默认地址（如 Anthropic 默认 `https://api.anthropic.com`），导致请求失败。

```ini
# scripts/.env
base_url=https://svip.kapon.cloud
```

脚本 `add` 命令会自动读取此值。也可以通过 `--base-url` 参数覆盖：

```bash
python3 channel_glm.py add --base-url "https://custom.api.com"
```

## 使用示例

### 测试连通性

```bash
# 测试所有 GLM 相关渠道（默认动作）
python3 channel_glm.py

# 测试指定渠道
python3 channel_glm.py test --id 33

# 测试指定模型
python3 channel_glm.py test --id 33 --model glm-5.1

# 测试所有 Claude 渠道
python3 channel_claude.py
```

### 查询渠道

```bash
python3 channel_glm.py list
python3 channel_codex.py list
python3 channel_claude.py list
python3 channel_images.py list
```

### 添加渠道

```bash
# 使用默认配置（从 .env 读取 key 和 base_url）
python3 channel_glm.py add

# 自定义参数
python3 channel_glm.py add --name "GLM-主力" --models "glm-5.1,glm-5.2" --priority 100

# 指定不同上游
python3 channel_glm.py add --base-url "https://other.api.com" --priority 200
```

### 修改渠道

```bash
# 修改优先级
python3 channel_glm.py update 33 --priority 200

# 修改模型列表
python3 channel_codex.py update 34 --models "gpt-5.5,gpt-5.4"

# 禁用渠道
python3 channel_glm.py update 33 --status 2

# 启用渠道
python3 channel_glm.py update 33 --status 1

# 同时修改多个字段
python3 channel_claude.py update 35 --priority 100 --weight 50 --status 1
```

### 删除渠道

```bash
python3 channel_glm.py delete 33
```

## 测试结果解读

| 状态 | 含义 |
|------|------|
| ✅ time=Xs | 连通正常，耗时 X 秒 |
| ❌ 令牌 IP 访问受限 | kapon 令牌有 IP 白名单，服务器不在白名单内 |
| ❌ 身份验证失败 | Key 无效或过期 |
| ❌ You are not authorized to use model X | 令牌无该模型权限，需换模型或联系 kapon 开权限 |
| ❌ 令牌不允许调用该模型 | 同上 |
| ❌ 令牌状态不可用 | 令牌被禁用 |
| ❌ bad response status code 404 | 上游地址错误或模型不存在 |

## 添加新渠道的完整流程

1. 确认 `scripts/.env` 中有对应的 key 和 `base_url`
2. 添加渠道：`python3 channel_xxx.py add`
3. 测试连通：`python3 channel_xxx.py test --id <新ID>`
4. 如需调整：`python3 channel_xxx.py update <ID> --priority N`

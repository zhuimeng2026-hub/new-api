# NewAPI Failover 链路文档

**地址:** `https://aikey.aixifs.com`
**更新时间:** 2026-05-06
**Token:** `OpenClaw-Unified-Token` (token_id=11)

---

## 渠道总览

| 优先级 | ID | 名称 | 类型 | 状态 | 模型数 |
|--------|-----|------|------|------|--------|
| 1000 | 9 | ModelScope | OpenAI | ✅ | 8 |
| 999 | 10 | DeepSeek | DeepSeek | ✅ | 6 |
| 500 | 12 | 小米MiMo | MiMo | ✅ | 9 |
| 300 | 6 | 火山引擎(Coding) | OpenAI | ✅ | 2 |
| 200 | 13 | SCNET-Coding | MiniMax | ✅ | 1 |
| 0 | 5 | 智谱GLM(Coding) | 智谱GLM | ✅ | 10 |
| 0 | 7 | SCNET-ALL | OpenAI | ✅ | 19 |
| 0 | 2 | 智谱GLM-5(Anthropic) | 智谱GLM | ✅ | 6 |
| 0 | 11 | ModelScope-文生图 | OpenAI | ✅ | 1 |
| 0 | 1 | 智谱BigModel | 智谱BigModel | ❌ | 17 |

---

## 跨渠道 Failover 策略

NewAPI 的 failover 基于**请求模型名**匹配渠道模型列表。当多个渠道的模型列表包含同一模型名时，按优先级依次尝试。

**跨模型名 failover：** 通过 `model_mapping` 实现不同模型间的切换。在低优先级渠道的模型列表中添加主渠道的模型名，再用 model_mapping 映射到该渠道实际支持的模型。

**配置方法：**
1. 在 fallback 渠道的 `models` 中添加主渠道的模型名（如 `deepseek-v4-pro`）
2. 设置 `model_mapping` 将其映射到 fallback 渠道的实际模型（如 `mimo-v2.5-pro`）
3. 请求链路：主渠道失败 → fallback 渠道匹配到同名模型 → mapping 转换 → 调用实际模型

**当前已配置的跨渠道映射：**

| 请求模型 | 主渠道 (优先级) | fallback 渠道 (优先级) | mapping |
|----------|----------------|----------------------|---------|
| deepseek-v4-pro | DeepSeek (999) | 小米MiMo (500) | deepseek-v4-pro → mimo-v2.5-pro |
| ZhipuAI/GLM-5.1 | DeepSeek (999) | 智谱GLM-5(Anthropic) (0) | ZhipuAI/GLM-5.1 → deepseek-v4-flash |
| ZhipuAI/GLM-4.7-Flash | DeepSeek (999) | — | ZhipuAI/GLM-4.7-Flash → deepseek-v4-flash |
| claude-opus-4-7 | 智谱GLM-5(Anthropic) (0) | — | claude-opus-4-7 → glm-5.1 |

---

## 按模型的 Failover 链

### DeepSeek 系列

**deepseek-v4-pro**
```
DeepSeek (999) → 小米MiMo (500, 映射→mimo-v2.5-pro)
```

**deepseek-v4-flash**
```
DeepSeek (999) → [无 fallback]
```

**deepseek-chat / deepseek-reasoner**
```
DeepSeek (999) → [无 fallback]
```

> ⚠️ deepseek-v4-flash / deepseek-chat / deepseek-reasoner 无 fallback。

### MiMo 系列

**mimo-v2.5-pro**
```
小米MiMo (500) → [无 fallback]
```

**mimo-v2.5 / mimo-v2-pro / mimo-v2-omni / mimo-v2-flash**
```
小米MiMo (500) → [无 fallback]
```

**mimo-v2-tts / mimo-v2.5-tts / mimo-v2.5-tts-voiceclone / mimo-v2.5-tts-voicedesign**
```
小米MiMo (500) → [无 fallback]
```

> ⚠️ MiMo 全系列单点。

### GLM 系列

**glm-4.7**
```
火山引擎 (300) → 智谱GLM(Coding) (0) → SCNET-ALL (0)
```

**glm-5.1**
```
火山引擎 (300) → 智谱GLM-5(Anthropic) (0)
```

**glm-5 / glm-5-turbo**
```
智谱GLM-5(Anthropic) (0) → [无 fallback]
```

**glm-4-plus / glm-4 / glm-4-air / glm-4-airx / glm-4-long / glm-4-flash / glm-4-flashx**
```
智谱GLM(Coding) (0) → 智谱BigModel (0, ❌禁用)
```

### ZhipuAI 映射模型

**ZhipuAI/GLM-5.1** → model_mapping 映射到 `deepseek-v4-flash`
```
DeepSeek (999) → 火山引擎 (300, 但模型名不匹配) → 智谱GLM-5(Anthropic) (0)
```

**ZhipuAI/GLM-4.7-Flash** → model_mapping 映射到 `deepseek-v4-flash`
```
DeepSeek (999) → [无 fallback]
```

### MiniMax 系列

**MiniMax-M2.5**
```
SCNET-Coding (200) → SCNET-ALL (0)
```

### Claude 映射模型（走智谱GLM-5渠道）

**claude-opus-4-7** → model_mapping 映射到 `glm-5.1`
```
智谱GLM-5(Anthropic) (0) → ❌ 401 认证失败
```

**claude-sonnet-4-6** → model_mapping 映射到 `glm-5-turbo`
```
智谱GLM-5(Anthropic) (0) → ❌ 401 认证失败
```

> ⚠️ Claude 系列映射到智谱但认证失败，实际不可用。

### 文生图

**Qwen/Qwen-Image**
```
ModelScope-文生图 (0) → [无 fallback]
```

---

## 已知问题

| 问题 | 影响 | 状态 |
|------|------|------|
| DeepSeek 部分模型无 fallback | deepseek-v4-flash/chat/reasoner 渠道故障时不可用 | 待补充 |
| MiMo 无 fallback | 渠道故障时完全不可用 | 待补充渠道 |
| 智谱GLM-5 认证失败 (401) | claude-opus-4-7 等映射模型不可用 | 待排查 key |
| 智谱BigModel 已禁用 | GLM 系列 fallback 减少 | 待确认是否重新启用 |

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-05-06 | 删除 DeepSeek 渠道失效模型: deepseek-v3, deepseek-r1, deepseek-v4 |
| 2026-05-06 | 小米MiMo 渠道补充 API Key |
| 2026-05-06 | MiMo 渠道添加 deepseek-v4-pro 模型 + model_mapping，实现跨渠道 failover |
| 2026-05-06 | 新增「跨渠道 Failover 策略」章节 |
| 2026-05-06 | 初始文档创建 |

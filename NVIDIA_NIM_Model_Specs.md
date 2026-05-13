# NVIDIA NIM 大模型规格查询汇总

> 两次查询汇总，数据来源均为 NVIDIA 官方文档 + 各模型官方资料  
> 日期：2026-05-14

## 第一次查询：NVIDIA NIM 平台主要大模型规格

从 `docs.api.nvidia.com/nim/reference/` 逐个模型页面查询。

| 模型 | 总参数 | 激活参数 | 上下文窗口 | 最大输出 | 架构 |
|---|---|---|---|---|---|
| nemotron-3-super-120b-a12b | 120B | 12B | **1M** | 32,768 | LatentMoE (Mamba-2+MoE+Attention) |
| llama-3.3-nemotron-super-49b-v1.5 | 49B | 49B | **131K** | 32,768 | Dense Transformer (NAS) |
| mistral-large-3-675b-instruct-2512 | 675B | 41B | **256K** | 未公开 | MoE |
| llama-4-maverick-17b-128e-instruct | 17B×128E | 17B | **128K** | 未公开 | MoE (128 experts) |
| deepseek-v4-pro | 1.6T | 49B | **1M** | 未公开 | MoE (CSA + HCA hybrid) |
| qwen3.5-397b-a17b | 397B | 17B | **262K** (可扩至1M) | 32,768 (最高81,920) | Hybrid MoE + Gated DeltaNet |

### 未在 NVIDIA 文档站找到独立页面的模型

以下模型在 `docs.api.nvidia.com` 没有独立参考页（404 或不存在），规格来自各自官方来源：

| 模型 | 说明 |
|---|---|
| z-ai/glm-5.1 | NVIDIA 文档页 404 |
| z-ai/glm5 | 同上 |
| z-ai/glm4.7 | 同上 |
| mistralai/mistral-nemotron | 同上 |
| mistralai/mistral-medium-3.5-128b | 同上 |
| mistralai/mistral-small-4-119b-2603 | 同上 |
| mistralai/ministral-14b-instruct-2512 | 同上 |
| stepfun-ai/step-3.5-flash | 同上 |
| minimaxai/minimax-m2.7 | 同上 |

### 账号无权限的模型

| 模型 | 状态 |
|---|---|
| nvidia/llama-3.1-nemotron-70b-instruct | 404 — Function not found |
| nvidia/llama-3.1-nemotron-ultra-253b-v1 | 404 — Function not found |
| mistralai/mistral-large (v1) | 404 — Function not found |

---

## 第二次查询：GLM-5.1 / GLM-5-Turbo 官方规格

NVIDIA 文档站没有 GLM-5.1/GLM-5-Turbo 的独立页面（均返回 404）。通过 WebSearch 从 Z.AI 官方文档和智谱官方文档获取。

### GLM-5.1

| 项目 | 规格 |
|---|---|
| **总参数** | ~744B (744-754B) |
| **激活参数** | ~40B (40-42.7B) |
| **架构** | MoE，78 层 (3 dense + 75 MoE) + 1 MTP/NEXTN |
| **注意力** | MLA-DSA (Multi-head Latent Attention + DeepSeek Sparse Attention)，64 heads |
| **隐藏维度** | 6,144 |
| **上下文窗口** | **200K tokens** |
| **最大输出** | **128K tokens** (部分平台 131K) |
| **精度** | FP8，社区有 FP4 量化版 |
| **发布时间** | 2025/04/08 |
| **许可** | **MIT 开源** |
| **定位** | 对标 Claude Opus 4.6，支持 thinking、tool calling、结构化输出 |
| **特色** | 支持最长 **8 小时**连续自主 Agent 运行 |

来源：[Z.AI 开发者文档](https://docs.z.ai/guides/llm/glm-5.1)、[智谱AI 开放文档](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.1)

### GLM-5-Turbo

| 项目 | 规格 |
|---|---|
| **总参数** | 744B |
| **激活参数** | 40B-44B |
| **架构** | MoE，80 层 / 256 个专家 |
| **上下文窗口** | **200K** |
| **最大输出** | **128K** |
| **预训练数据** | 28.5T Tokens |
| **训练框架** | Slime（异步智能体强化学习） |
| **发布时间** | 2026/03/16 |
| **许可** | **闭源** |
| **定位** | 面向 OpenClaw/Agent 场景深度优化 |
| **评测** | ClawBench 93.9 / SWE-bench Verified 77.8 / Terminal-Bench 2.0 60.7 / BrowseComp 75.9 |
| **接入平台** | OpenRouter、Coze、美团、字节 TRAE 等 |

来源：[Z.AI 开发者文档](https://docs.z.ai/guides/llm/glm-5-turbo)、[智谱AI 开放文档](https://docs.bigmodel.cn/cn/guide/models/text/glm-5-turbo)

### GLM 系列对比

| | GLM-5.1 | GLM-5-Turbo |
|---|---|---|
| 上下文 | 200K | 200K |
| 最大输出 | 128K | 128K |
| 总参数 | ~744B | 744B |
| 许可 | MIT 开源 | 闭源 |
| 发布时间 | 2025/04 | 2026/03 |
| 专注方向 | 通用 / 长时自主 Agent | Agent / Tool Calling 深度优化 |

---

## 参考来源

- [NVIDIA NIM API 文档](https://docs.api.nvidia.com/nim/reference/llm-apis)
- [Nemotron-3-Super-120B](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b)
- [Llama-3.3-Nemotron-Super-49B-v1.5](https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_3-nemotron-super-49b-v1_5)
- [Llama-4-Maverick](https://docs.api.nvidia.com/nim/reference/meta-llama-4-maverick-17b-128e-instruct)
- [DeepSeek-V4-Pro](https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-pro)
- [Mistral-Large-3](https://docs.api.nvidia.com/nim/reference/mistralai-mistral-large-3-675b-instruct-2512)
- [Qwen3.5-397B](https://docs.api.nvidia.com/nim/reference/qwen-qwen3-5-397b-a17b)
- [GLM-5.1 — Z.AI 文档](https://docs.z.ai/guides/llm/glm-5.1)
- [GLM-5-Turbo — Z.AI 文档](https://docs.z.ai/guides/llm/glm-5-turbo)
- [智谱AI 开放文档 — GLM-5.1](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.1)
- [智谱AI 开放文档 — GLM-5-Turbo](https://docs.bigmodel.cn/cn/guide/models/text/glm-5-turbo)

# TODO / 二次开发进度

> new-api = `/opt/new-api`（Go AI 网关）. oversea-key = `/opt/keygen`（前端密钥生成器）.

---

## 一、已完成 — new-api

### 1.1 model_limits 修复
- **文件**: `middleware/distributor.go`
- **Commit**: `4993a0dd` (已推送)
- **内容**: 将 `model_limits` 校验移入 `if shouldSelectChannel` 块，避免视频/图片任务轮询 GET 请求（无 body → model 为空）被误拦截
- **状态**: 代码已推送，**等待构建部署**

### 1.2 doubao 适配器扩展
- **文件**: `relay/channel/task/doubao/constants.go`
- **Commit**: `8a576785` (已推送)
- **内容**: ModelList 新增 `doubao-seedance-2-0-260128` / `doubao-seedance-2-0-fast-260128` / `seedance-2-0` / `seedance-2-0-fast` / `doubao-seedance-2-0` / `doubao-seedance-2-0-fast`
- **状态**: 代码已推送，**等待构建部署**

### 1.3 渠道 24（DoubaoVideo, type=54）
- **位置**: PostgreSQL `channels` 表
- **配置**: type=54, name=火山引擎(DoubaoVideo-seedance), base_url=https://svip.kapon.cloud, models=seedance-2-0-fast
- **说明**: 直插数据库创建，key 复用渠道 23（开朋网络）
- **状态**: 渠道已建，**等待代码部署后测试**

### 1.4 运营脚本
- `monitor.sh` / `monitor_feishu.sh` — 渠道健康监控与飞书告警
- `list_channels.sh` / `test_models.sh` / `test_mobile.sh` — 频道查询与模型测试
- `newapi-db.sh` — 数据库备份维护
- `channel_backup_20260514_064015.json` — 频道配置备份

---

## 二、已完成 — oversea-key (keygen.aixifs.com)

### 2.1 独立子域部署
- **域名**: `keygen.aixifs.com`（独立 Nginx server block, 反代 `127.0.0.1:3001`）
- **前端**: Vue 3 + Vite — `vite.config.ts` 含 `base: '/keygen/'`
- **后端**: Go + Gin — 路由均 `/keygen/api/*` 前缀

### 2.2 密钥生成器（核心功能）
- `POST /keygen/api/generate` — 生成 API key（指定模型+额度）
- `GET /keygen/api/models` — 获取可用模型列表（按分类）
- 左侧边栏模型选择 + 额度卡片 + 生成按钮

### 2.3 用量监控（UsageMonitor.vue）
- `POST /keygen/api/usage` — 查询 token 用量
- 前端自动使用已生成 key，无需手动输入

### 2.4 图片生成（ImageGenerator.vue）
- `POST /keygen/api/image` — 文生图（通过 new-api 代理）
- Prompt 输入框 4 行，自动使用已生成 key

### 2.5 视频生成（VideoGenerator.vue）★
- `POST /keygen/api/video` — 提交视频任务
- `GET /keygen/api/video/:task_id` — 后端 goroutine 轮询状态
- 前端 5s 间隔轮询 + 状态展示 + 视频元素渲染
- 模型下拉框（optgroup: Sora, Kling, MiniMax, Vidu, Jimeng）
- 自动使用已生成 key

---

## 三、待完成

### 3.1 视频生成全链路测试 ⏳
- **阻塞**: 两笔 new-api commit 未部署
- **依赖**: 构建机 build + reload new-api
- **测试步骤**:
  1. 生成含 `seedance-2-0-fast` 的 key → oversea-key POST 提交
  2. 确认请求路由至渠道 24 (type=54) → doubao 适配器
  3. 验证 svip.kapon.cloud 是否代理 `/api/v3/contents/generations/tasks` 路径
  4. GET 轮询确认不出现 model_limits 拦截 → 拿到视频 URL
- **Plan B（若 svip.kapon 不代理 ark 原生路径）**: 改为直连 `https://ark.cn-beijing.volces.com`，但需火山原生 API Key

### 3.2 oversea-key 项目规范化
- `/opt/keygen` 目录不是 git 仓库，代码无版本控制
- handler/video.go 的切片越界 panic 已修复但未 git 追踪
- 建议建立 git 仓库或纳入 CI

---

## 四、关键信息速查

| 项目 | 值 |
|------|-----|
| new-api 管理后台 | `https://aikey.aixifs.com` |
| new-api admin key | `/4i0T9XxVmZC4ud49ajc+K+3QBLQ` |
| oversea-key 服务 | `keygen.aixifs.com → 127.0.0.1:3001` |
| 渠道 23 (开朋) | type=1, `https://svip.kapon.cloud`, 150+ 模型 |
| 渠道 24 (DoubaoVideo) | type=54, `https://svip.kapon.cloud`, seedance-2-0-fast |
| 火山 Ark 文档 | https://www.volcengine.com/docs/82379/1520757 |
| PostgreSQL | `docker exec postgres psql -U root -d new-api` |

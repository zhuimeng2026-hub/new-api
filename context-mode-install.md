# context-mode 安装指南（Claude Code + 轻量云/代理环境）

## 适用场景

- 轻量云服务器（带宽/IO 有限）
- 代理/镜像环境
- 不依赖 GitHub 直接拉取

## 步骤

### 1. 配置 npm 镜像

```bash
npm config set registry https://mirrors.tencentyun.com/npm
```

### 2. 全局安装 context-mode

```bash
npm install -g context-mode
```

> better-sqlite3 装不上可跳过（optional dependency），FTS5 全文搜索降级为内存搜索，其余功能不受影响。

### 3. 确认路径

```bash
ls "$(npm root -g)/context-mode/start.mjs"
```

### 4. 注册为 MCP 服务器

编辑 `~/.claude/settings.json`，在根对象中添加：

```json
"mcpServers": {
  "context-mode": {
    "command": "node",
    "args": ["/usr/lib/node_modules/context-mode/start.mjs"]
  }
}
```

> `/usr/lib/node_modules` 替换为 `npm root -g` 的实际输出。

### 5. 重启 Claude Code，验证

```
ctx stats
```

能正常输出即生效。

## 为什么不用插件市场？

插件市场方式会触发 `git clone` + 全量 `npm install`（含 ts/esbuild/vite 等 dev 依赖，共约 135MB），在轻量云上容易超时或卡死。直接 npm 全局 + MCP 注册只需拉 bundle 包，几秒到几十秒完成。

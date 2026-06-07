#!/usr/bin/env bash
# deploy_gpt_image2_logs.sh — 无人值守部署 gpt-image-2 日志展示功能
# 用法: nohup bash deploy_gpt_image2_logs.sh &
# 日志: /opt/new-api/deploy_gpt_image2_logs_<timestamp>.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${SCRIPT_DIR}/deploy_gpt_image2_logs_${TIMESTAMP}.log"
PLAN_FILE="/root/.claude/plans/moonlit-launching-rose.md"
TARGET_FILE="${SCRIPT_DIR}/web/src/hooks/usage-logs/useUsageLogsData.jsx"
PROMPT_FILE="/tmp/deploy_gpt_image2_prompt_${TIMESTAMP}.txt"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "============================================"
echo " gpt-image-2 日志展示功能 — 无人值守部署"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# 前置检查
for cmd in claude bun; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "[ERROR] $cmd 未安装"; exit 1
  fi
done

for f in "$PLAN_FILE" "$TARGET_FILE"; do
  if [[ ! -f "$f" ]]; then
    echo "[ERROR] 文件不存在: $f"; exit 1
  fi
done

echo "[INFO] 计划文件: $PLAN_FILE"
echo "[INFO] 目标文件: $TARGET_FILE"
echo "[INFO] 日志文件: $LOG_FILE"

# 备份
BACKUP_FILE="${TARGET_FILE}.bak.${TIMESTAMP}"
cp "$TARGET_FILE" "$BACKUP_FILE"
echo "[INFO] 已备份: $BACKUP_FILE"

# 写入 prompt 文件
cat > "$PROMPT_FILE" << 'EOF'
请严格按照 /root/.claude/plans/moonlit-launching-rose.md 中的方案，修改 web/src/hooks/usage-logs/useUsageLogsData.jsx。

具体要求:
1. 在文件顶部（import 语句之后，useLogsData 函数之前）添加两个纯函数:
   - isImageLog(log): 检测图像模型日志（model_name含image / content含"大小.*品质.*生成数量" / other.request_conversion含openai_image）
   - parseImageContent(content): 解析content中的尺寸/品质/生成数量

2. 在 setLogsFormat() 的 type===2 分支中，在 claude 和 audio 分支之后、通用 else 之前，插入 isImageLog 分支:
   - 成功请求: 展示尺寸、品质、生成数量、请求路径、计费方式、单价、token、耗时
   - 失败请求: 展示错误码、错误类型、错误代码、请求路径、错误详情、耗时
   - 计费过程复用现有 renderModelPrice

3. 不要修改任何现有逻辑，只插入新代码。
4. 修改完成后输出修改摘要。
EOF

echo "[INFO] Prompt 文件: $PROMPT_FILE"

# 执行 claude CLI（通过 stdin 传入 prompt）
echo ""
echo "[INFO] 正在执行 claude CLI (非交互模式)..."
echo ""

if cat "$PROMPT_FILE" | claude -p --output-format text \
  --add-dir /root/.claude/plans \
  --allowedTools "Read,Edit" 2>&1; then
  echo ""
  echo "[SUCCESS] claude CLI 执行完成"
  EXIT_CODE=0
else
  EXIT_CODE=$?
  echo ""
  echo "[ERROR] claude CLI 退出码: $EXIT_CODE"
fi

# 清理临时文件
rm -f "$PROMPT_FILE"

# 失败时回滚
if [[ $EXIT_CODE -ne 0 ]]; then
  echo "[INFO] 正在恢复备份..."
  cp "$BACKUP_FILE" "$TARGET_FILE"
  echo "[INFO] 已恢复备份"
  exit 1
fi

# 验证
echo ""
echo "[INFO] 验证修改..."
for func in isImageLog parseImageContent; do
  if grep -q "$func" "$TARGET_FILE"; then
    echo "[OK] $func 已添加"
  else
    echo "[WARN] $func 未找到"
  fi
done

# 前端构建
echo ""
echo "[INFO] 执行前端构建..."
cd "${SCRIPT_DIR}/web"
if bun run build 2>&1 | tail -5; then
  echo "[OK] 前端构建成功"
else
  echo "[WARN] 前端构建失败，请检查代码"
fi

echo ""
echo "============================================"
echo " 部署完成: $(date '+%Y-%m-%d %H:%M:%S')"
echo " 日志: $LOG_FILE"
echo " 备份: $BACKUP_FILE"
echo "============================================"

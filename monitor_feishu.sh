#!/bin/bash
# ============================================================
# new-api 监控脚本 (飞书自建应用版)
# 每5分钟通过 cron 执行, 异常时推送飞书消息
#
# 前置准备:
#   1. 飞书开发者后台 → 自建应用 → 权限管理 → 开启 im:message:send
#   2. 把机器人拉到目标群聊
#   3. 获取群聊 chat_id 或用户 open_id
#
# 用法:
#   ./monitor_feishu.sh           # 单次检查
#   ./monitor_feishu.sh --cron    # cron 模式 (静默, 仅异常时通知)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_FILE="/tmp/newapi-feishu-monitor.state"
TOKEN_FILE="/tmp/newapi-feishu-token.json"
ALERT_LOG="/tmp/newapi-feishu-alert.log"

# ---- 本地告警日志 (飞书通知失败时也有据可查) ----
alert_log() {
    local title="$1" content="$2"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${title}" >> "$ALERT_LOG"
    echo "${content}" >> "$ALERT_LOG"
    echo "---" >> "$ALERT_LOG"
}

# ---- 飞书配置 ----
FEISHU_APP_ID="${FEISHU_APP_ID:-cli_a95ee4e7f1ba5bb4}"
FEISHU_APP_SECRET="${FEISHU_APP_SECRET:-mv1uRalnsXqfKDsskIFcTdVaANMV01Ot}"
# 消息接收者: chat_id (群聊) 或 open_id (个人)
FEISHU_RECEIVE_ID="${FEISHU_RECEIVE_ID:-}"
FEISHU_RECEIVE_TYPE="${FEISHU_RECEIVE_TYPE:-chat_id}"  # chat_id 或 open_id

# ---- new-api 配置 (从 .env 读取) ----
if [ -f "$SCRIPT_DIR/.env" ]; then
    API_URL=$(grep "^new_api_url=" "$SCRIPT_DIR/.env" | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
    ADMIN_KEY=$(grep "^new_admin_key=" "$SCRIPT_DIR/.env" | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
    API_USER=$(grep "^New-Api-User=" "$SCRIPT_DIR/.env" | cut -d'=' -f2- | tr -d '\r')
fi
API_URL="${API_URL:-https://aikey.aixifs.com}"
API_URL="${API_URL%/}"
ADMIN_KEY="${ADMIN_KEY:-}"
API_USER="${API_USER:-1}"

QUOTA_THRESHOLD="${QUOTA_THRESHOLD:-0}"
MONITOR_CHANNELS="${MONITOR_CHANNELS:-}"

CRON_MODE=false
[ "${1:-}" = "--cron" ] && CRON_MODE=true

# ---- 飞书 API ----
feishu_get_token() {
    # 缓存 token (有效期 2 小时)
    if [ -f "$TOKEN_FILE" ]; then
        local cached_ts=$(jq -r '.ts // 0' "$TOKEN_FILE" 2>/dev/null || echo 0)
        local now_ts=$(date +%s)
        if [ $((now_ts - cached_ts)) -lt 7100 ]; then
            jq -r '.token' "$TOKEN_FILE"
            return
        fi
    fi

    local resp
    resp=$(curl -s --connect-timeout 10 --max-time 15 \
        -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
        -H "Content-Type: application/json" \
        -d "{\"app_id\":\"${FEISHU_APP_ID}\",\"app_secret\":\"${FEISHU_APP_SECRET}\"}")

    local code
    code=$(echo "$resp" | jq -r '.code // -1')
    if [ "$code" != "0" ]; then
        echo "ERROR: 获取飞书 token 失败: $resp" >&2
        return 1
    fi

    local token
    token=$(echo "$resp" | jq -r '.tenant_access_token')
    echo "{\"token\":\"$token\",\"ts\":$(date +%s)}" > "$TOKEN_FILE"
    echo "$token"
}

feishu_send() {
    local title="$1" content="$2"
    if [ -z "$FEISHU_RECEIVE_ID" ]; then
        $CRON_MODE || echo "[通知] 未配置 FEISHU_RECEIVE_ID, 跳过"
        $CRON_MODE || echo "  标题: $title"
        $CRON_MODE || echo "  内容: $content"
        return
    fi

    local token
    token=$(feishu_get_token) || return

    # 构建飞书 interactive 卡片消息
    local card
    card=$(jq -n \
        --arg title "$title" \
        --arg content "$content" \
        --arg time "$(date '+%Y-%m-%d %H:%M:%S')" \
        --arg target "$API_URL" \
        '{
            config: {wide_screen_mode: true},
            header: {
                title: {tag: "plain_text", content: "new-api 监控告警"},
                template: "red"
            },
            elements: [
                {tag: "div", text: {tag: "lark_md", content: "\($content)"}},
                {tag: "hr"},
                {tag: "note", elements: [
                    {tag: "plain_text", content: "\($time) | 目标: \($target)"}
                ]}
            ]
        }')

    local resp
    resp=$(curl -s --connect-timeout 10 --max-time 15 \
        -X POST "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=${FEISHU_RECEIVE_TYPE}" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "{\"receive_id\":\"${FEISHU_RECEIVE_ID}\",\"msg_type\":\"interactive\",\"content\":$(echo "$card" | jq -c . | jq -R -s '.')}")

    local code
    code=$(echo "$resp" | jq -r '.code // -1')
    if [ "$code" != "0" ]; then
        echo "[通知失败] 飞书返回: $resp" >&2
    else
        $CRON_MODE || echo "[已通知] 飞书消息已发送"
    fi
}

# ---- new-api API 调用 ----
api_call() {
    local path="$1"
    curl -s -w "\n%{http_code}" --connect-timeout 10 --max-time 30 \
        -H "Authorization: ${ADMIN_KEY}" \
        -H "New-Api-User: ${API_USER}" \
        "${API_URL}/api${path}" 2>/dev/null || echo -e "\n000"
}

# ---- 检查 1: 服务存活 ----
check_service_alive() {
    $CRON_MODE || echo "[检查1] 服务存活..."
    local resp http_code body
    resp=$(curl -s -w "\n%{http_code}" --connect-timeout 10 --max-time 15 \
        "${API_URL}/api/status" 2>/dev/null || echo -e "\n000")
    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        alert_log "服务不可达" "HTTP状态码: ${http_code}\n地址: ${API_URL}/api/status"
        feishu_send "服务不可达" "**HTTP 状态码**: ${http_code}\n**地址**: ${API_URL}/api/status"
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        local msg=$(echo "$body" | jq -r '.message // "unknown"')
        alert_log "服务异常" "${msg}"
        feishu_send "服务异常" "${msg}"
        return 1
    fi
    $CRON_MODE || echo "  OK"
    return 0
}

# ---- 检查 2: 错误日志 ----
check_error_logs() {
    $CRON_MODE || echo "[检查2] 错误日志 (最近5分钟)..."

    local now_ts end_ts start_ts
    now_ts=$(date +%s)
    end_ts=$now_ts
    start_ts=$((end_ts - 300))

    local last_ts=$start_ts
    if [ -f "$STATE_FILE" ]; then
        last_ts=$(grep "^last_ts=" "$STATE_FILE" 2>/dev/null | cut -d'=' -f2 || echo "$start_ts")
    fi

    local resp http_code body
    resp=$(api_call "/log/?type=5&start_timestamp=${last_ts}&end_timestamp=${end_ts}&page=0&page_size=50")
    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    echo "last_ts=$end_ts" > "$STATE_FILE"

    if [ "$http_code" != "200" ]; then
        feishu_send "错误日志 API 异常" "**HTTP 状态码**: ${http_code}\n**地址**: /api/log?type=5"
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        return 0
    fi

    local total
    total=$(echo "$body" | jq -r '.data.total // 0')
    if [ "$total" -eq 0 ]; then
        $CRON_MODE || echo "  无错误日志"
        return 0
    fi

    local items
    items=$(echo "$body" | jq -r '.data.items[:10][] | "- [\(.channel_name // "system")] \(.model_name // "") → \(.content[:100])"' 2>/dev/null || echo "")
    local t1 t2
    t1=$(date -d "@${last_ts}" '+%H:%M:%S' 2>/dev/null || date '+%H:%M:%S')
    t2=$(date '+%H:%M:%S')

    local content="**时间**: ${t1} ~ ${t2}\n"
    content+="${items}\n\n**共 ${total} 条错误**"

    alert_log "发现 ${total} 条错误日志" "$content"
    feishu_send "发现 ${total} 条错误日志" "$content"
    return 1
}

# ---- 检查 3: 渠道报错 ----
check_channel_errors() {
    $CRON_MODE || echo "[检查3] 渠道报错分析..."

    local now_ts end_ts start_ts
    now_ts=$(date +%s)
    end_ts=$now_ts
    start_ts=$((end_ts - 300))

    local resp http_code body
    resp=$(api_call "/log/?type=5&start_timestamp=${start_ts}&end_timestamp=${end_ts}&page=0&page_size=200")
    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        feishu_send "渠道报错 API 异常" "**HTTP 状态码**: ${http_code}\n**地址**: /api/log?type=5"
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        return 0
    fi

    local total
    total=$(echo "$body" | jq -r '.data.total // 0')
    if [ "$total" -eq 0 ]; then
        $CRON_MODE || echo "  渠道无报错"
        return 0
    fi

    # 按渠道归类
    local channel_summary
    channel_summary=$(echo "$body" | jq -r '[.data.items[] | select(.channel != 0 and .channel_name != "")] | group_by(.channel_name) | .[] | "**\(.[0].channel_name)**: \(length)次 | \(([.[].model_name] | unique | join(", ")))"' 2>/dev/null || echo "")

    if [ -n "$channel_summary" ]; then
        local content="${channel_summary}\n\n**共 ${total} 条渠道错误**"
        alert_log "渠道报错汇总" "$content"
        feishu_send "渠道报错汇总" "$content"
        return 1
    fi
    return 0
}

# ---- 检查 4: 额度异常 ----
check_quota_anomaly() {
    $CRON_MODE || echo "[检查4] 额度消耗..."

    local now_ts end_ts start_ts
    now_ts=$(date +%s)
    end_ts=$now_ts
    start_ts=$((end_ts - 300))

    local resp http_code body
    resp=$(api_call "/log/stat?type=2&start_timestamp=${start_ts}&end_timestamp=${end_ts}")
    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        feishu_send "额度统计 API 异常" "**HTTP 状态码**: ${http_code}\n**地址**: /api/log/stat?type=2"
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        return 0
    fi

    local quota rpm tpm
    quota=$(echo "$body" | jq -r '.data.quota // 0')
    rpm=$(echo "$body" | jq -r '.data.rpm // 0')
    tpm=$(echo "$body" | jq -r '.data.tpm // 0')

    local prev_quota=0
    if [ -f "$STATE_FILE" ]; then
        prev_quota=$(grep "^prev_quota=" "$STATE_FILE" 2>/dev/null | cut -d'=' -f2 || echo 0)
    fi

    echo "prev_quota=$quota" >> "$STATE_FILE"
    echo "prev_rpm=$rpm" >> "$STATE_FILE"
    echo "prev_tpm=$tpm" >> "$STATE_FILE"

    local quota_diff=$((quota - prev_quota))
    $CRON_MODE || echo "  5分钟消耗: quota=${quota}, rpm=${rpm}, tpm=${tpm}"

    if [ "${QUOTA_THRESHOLD:-0}" -gt 0 ] && [ "$quota_diff" -gt "$QUOTA_THRESHOLD" ]; then
        alert_log "额度消耗异常" "5分钟内消耗: ${quota_diff} (阈值: ${QUOTA_THRESHOLD})\nRPM: ${rpm} | TPM: ${tpm}"
        feishu_send "额度消耗异常" "**5分钟内消耗**: ${quota_diff} (阈值: ${QUOTA_THRESHOLD})\n**RPM**: ${rpm} | **TPM**: ${tpm}"
        return 1
    fi
    return 0
}

# ---- 主流程 ----
main() {
    if [ "${1:-}" = "--test" ]; then
        feishu_send "测试消息" "**new-api 监控测试**\n> 飞书通知链路正常\n> 目标: ${API_URL}\n> 时间: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "测试消息已发送"
        exit 0
    fi

    local errors=0
    $CRON_MODE || echo "======== $(date '+%Y-%m-%d %H:%M:%S') ========"

    check_service_alive || ((errors++))
    if [ "$errors" -eq 0 ]; then
        check_error_logs || ((errors++))
        check_channel_errors || ((errors++))
        check_quota_anomaly || ((errors++))
    fi

    if [ "$errors" -eq 0 ]; then
        $CRON_MODE || echo "全部检查通过"
    else
        $CRON_MODE || echo "发现 ${errors} 项异常"
    fi
    $CRON_MODE || echo ""
}

main "$@"

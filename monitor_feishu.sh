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
#
# 告警冷却:
#   服务不可达: 20分钟
#   错误日志:   15分钟
#   额度异常:   30分钟
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

# ---- 状态文件读写 ----
read_state() {
    local key="$1"
    [ -f "$STATE_FILE" ] || return 1
    grep "^${key}=" "$STATE_FILE" 2>/dev/null | tail -1 | cut -d'=' -f2-
}

write_state() {
    local key="$1" value="$2"
    local tmp="${STATE_FILE}.tmp"
    if [ -f "$STATE_FILE" ]; then
        grep -v "^${key}=" "$STATE_FILE" > "$tmp" 2>/dev/null || true
    else
        > "$tmp"
    fi
    echo "${key}=${value}" >> "$tmp"
    mv "$tmp" "$STATE_FILE"
}

# ---- 告警去重 (冷却期内不重复发送) ----
should_send() {
    local alert_key="$1" cooldown="$2"
    local last_sent
    last_sent=$(read_state "last_alert_${alert_key}" 2>/dev/null || echo "")
    local now
    now=$(date +%s)
    if [ -n "$last_sent" ] && [ "$((now - last_sent))" -lt "$cooldown" ]; then
        return 1
    fi
    write_state "last_alert_${alert_key}" "$now"
    return 0
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
    API_USER=$(grep "^New-Api-User=" "$SCRIPT_DIR/.env" | head -1 | cut -d'=' -f2- | tr -d '\r')
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
        local cached_ts
        cached_ts=$(jq -r '.ts // 0' "$TOKEN_FILE" 2>/dev/null || echo 0)
        local now_ts
        now_ts=$(date +%s)
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
        local msg="HTTP状态码: ${http_code}\n地址: ${API_URL}/api/status"
        alert_log "服务不可达" "$msg"
        if should_send "down" 1200; then
            feishu_send "服务不可达" "**${msg}**"
        else
            $CRON_MODE || echo "  [冷却中] 服务不可达告警已跳过"
        fi
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        local err_msg
        err_msg=$(echo "$body" | jq -r '.message // "unknown"')
        alert_log "服务异常" "${err_msg}"
        if should_send "down" 1200; then
            feishu_send "服务异常" "${err_msg}"
        else
            $CRON_MODE || echo "  [冷却中] 服务异常告警已跳过"
        fi
        return 1
    fi
    $CRON_MODE || echo "  OK"
    return 0
}

# ---- 检查 2: 错误日志 + 渠道报错 (合并) ----
check_errors_combined() {
    $CRON_MODE || echo "[检查2] 错误日志+渠道分析..."

    local now_ts end_ts start_ts
    now_ts=$(date +%s)
    end_ts=$now_ts
    start_ts=$((end_ts - 300))

    local last_ts
    last_ts=$(read_state "last_ts" 2>/dev/null || echo "$start_ts")
    write_state "last_ts" "$end_ts"

    local resp http_code body
    resp=$(api_call "/log/?type=5&start_timestamp=${last_ts}&end_timestamp=${end_ts}&page=0&page_size=200")
    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        alert_log "错误日志API异常" "HTTP: ${http_code}"
        if should_send "error" 900; then
            feishu_send "错误日志 API 异常" "**HTTP 状态码**: ${http_code}\n**地址**: /api/log?type=5"
        fi
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
        $CRON_MODE || echo "  无错误"
        return 0
    fi

    # 构建合并消息: 错误摘要 + 渠道归类
    local t1 t2
    t1=$(date -d "@${last_ts}" '+%H:%M:%S' 2>/dev/null || date '+%H:%M:%S')
    t2=$(date '+%H:%M:%S')

    local content
    content="**时间**: ${t1} ~ ${t2}  |  **共 ${total} 条**\n\n"

    # 错误摘要 (前8条)
    local items
    items=$(echo "$body" | jq -r '.data.items[:8][] | "- [\(.channel_name // "system")] \(.model_name // "") → \(.content[:80])"' 2>/dev/null || echo "")
    if [ -n "$items" ]; then
        content+="**错误详情:**\n${items}\n"
    fi

    # 渠道归类
    local channel_summary
    channel_summary=$(echo "$body" | jq -r '[.data.items[] | select(.channel != 0 and .channel_name != "")] | group_by(.channel_name) | .[] | "> **\(.[0].channel_name)**: \(length)次 | \([.[].model_name] | unique | join(", "))"' 2>/dev/null || echo "")

    if [ -n "$channel_summary" ]; then
        content+="\n**按渠道:**\n${channel_summary}"
    fi

    alert_log "发现 ${total} 条错误" "$content"
    if should_send "error" 900; then
        feishu_send "发现 ${total} 条错误" "$content"
    else
        $CRON_MODE || echo "  [冷却中] 错误告警已跳过"
    fi
    return 1
}

# ---- 检查 3: 额度异常 ----
check_quota_anomaly() {
    $CRON_MODE || echo "[检查3] 额度消耗..."

    if [ "${QUOTA_THRESHOLD:-0}" -le 0 ]; then
        $CRON_MODE || echo "  未设置阈值, 跳过"
        return 0
    fi

    local now_ts end_ts start_ts
    now_ts=$(date +%s)
    end_ts=$now_ts
    start_ts=$((end_ts - 300))

    local resp http_code body
    resp=$(api_call "/log/stat?type=2&start_timestamp=${start_ts}&end_timestamp=${end_ts}")
    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        alert_log "额度统计API异常" "HTTP: ${http_code}"
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

    local prev_quota
    prev_quota=$(read_state "prev_quota" 2>/dev/null || echo "0")
    write_state "prev_quota" "$quota"

    local quota_diff=$((quota - prev_quota))
    $CRON_MODE || echo "  5分钟消耗: quota=${quota_diff}, rpm=${rpm}, tpm=${tpm}"

    if [ "$quota_diff" -gt "$QUOTA_THRESHOLD" ]; then
        local content
        content="**5分钟内消耗**: ${quota_diff} (阈值: ${QUOTA_THRESHOLD})\n**RPM**: ${rpm} | **TPM**: ${tpm}"
        alert_log "额度消耗异常" "$content"
        if should_send "quota" 1800; then
            feishu_send "额度消耗异常" "$content"
        else
            $CRON_MODE || echo "  [冷却中] 额度异常告警已跳过"
        fi
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
        check_errors_combined || ((errors++))
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

#!/bin/bash
# ============================================================
# new-api 监控脚本
# 每5分钟检查一次远程 new-api 服务，发现异常通过企业微信通知
#
# 检查项:
#   1. 服务存活    — GET /api/status 是否正常响应
#   2. 错误日志    — 最近5分钟是否有 type=5 的错误日志
#   3. 渠道报错    — 错误日志中按渠道归类，识别故障渠道
#   4. 额度异常    — 消费额度/rpm/tpm 是否异常飙升
#
# 用法:
#   ./monitor.sh                           # 单次检查
#   ./monitor.sh --cron                    # cron 模式 (静默，仅异常时告警)
#
# 环境变量 (或写入 .env):
#   new_api_url        — new-api 服务地址
#   new_admin_key      — new-api 管理员 access token
#   WECHAT_WEBHOOK_KEY — 企业微信机器人 webhook key
#   MONITOR_CHANNELS   — 要重点监控的渠道ID，逗号分隔 (可选)
#   QUOTA_THRESHOLD    — 5分钟内消费额度告警阈值 (可选，默认 0 不检查)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_FILE="/tmp/newapi-monitor.state"
LAST_TS_FILE="/tmp/newapi-monitor.last_ts"

# ---- 加载配置 ----
if [ -f "$SCRIPT_DIR/.env" ]; then
    API_URL=$(grep "^new_api_url=" "$SCRIPT_DIR/.env" | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
    ADMIN_KEY=$(grep "^new_admin_key=" "$SCRIPT_DIR/.env" | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
fi

API_URL="${API_URL:-https://aikey.aixifs.com}"
ADMIN_KEY="${ADMIN_KEY:-}"
WEBHOOK_KEY="${WECHAT_WEBHOOK_KEY:-}"
MONITOR_CHANNELS="${MONITOR_CHANNELS:-}"
QUOTA_THRESHOLD="${QUOTA_THRESHOLD:-0}"

CRON_MODE=false
[ "${1:-}" = "--cron" ] && CRON_MODE=true

# ---- 颜色 ----
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

# ---- 工具函数 ----
now_ts() { date +%s; }
now_ts_ms() { date +%s%3N; }

log()  { $CRON_MODE || echo -e "$@"; }
ok()   { log "${GREEN}[OK]${NC} $*"; }
warn() { log "${YELLOW}[WARN]${NC} $*"; }
err()  { log "${RED}[ERR]${NC} $*"; }

# ---- 企业微信通知 ----
send_wechat() {
    local title="$1" content="$2"
    if [ -z "$WEBHOOK_KEY" ]; then
        log "${RED}[通知] 未配置 WECHAT_WEBHOOK_KEY，跳过通知${NC}"
        log "  标题: $title"
        log "  内容: $content"
        return
    fi

    local url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${WEBHOOK_KEY}"
    local body
    body=$(jq -n \
        --arg content "## ${title}\n${content}\n\n> 监控时间: $(date '+%Y-%m-%d %H:%M:%S')" \
        '{msgtype: "markdown", markdown: {content: $content}}')

    local resp
    resp=$(curl -s -X POST "$url" -H "Content-Type: application/json" -d "$body")
    local errcode
    errcode=$(echo "$resp" | jq -r '.errcode // "error"')
    if [ "$errcode" != "0" ]; then
        log "${RED}[通知失败] 企业微信返回: $resp${NC}"
    else
        log "${GREEN}[已通知] 企业微信消息已发送${NC}"
    fi
}

# ---- API 调用 ----
api_call() {
    local path="$1"
    local url="${API_URL}/api${path}"
    local resp
    resp=$(curl -s -w "\n%{http_code}" --connect-timeout 10 --max-time 30 \
        -H "Authorization: ${ADMIN_KEY}" \
        "$url" 2>/dev/null || echo -e "\n000")
    echo "$resp"
}

# ---- 检查 1: 服务存活 ----
check_service_alive() {
    log "${CYAN}[检查1] 服务存活...${NC}"
    local resp http_code
    resp=$(curl -s -w "\n%{http_code}" --connect-timeout 10 --max-time 15 \
        "${API_URL}/api/status" 2>/dev/null || echo -e "\n000")
    http_code=$(echo "$resp" | tail -1)
    local body
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        local msg="服务不可达，HTTP 状态码: ${http_code}"
        err "$msg"
        send_wechat "服务不可达" "> HTTP 状态码: **${http_code}**\n> 地址: ${API_URL}/api/status"
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        local msg="服务返回异常: $(echo "$body" | jq -r '.message // "unknown"')"
        err "$msg"
        send_wechat "服务异常" "> ${msg}"
        return 1
    fi
    ok "服务正常"
    return 0
}

# ---- 检查 2: 错误日志 ----
check_error_logs() {
    log "${CYAN}[检查2] 错误日志 (最近5分钟)...${NC}"

    local now_ms end_ts start_ts
    now_ms=$(now_ts_ms)
    end_ts=$((now_ms / 1000))
    start_ts=$((end_ts - 300))

    if [ ! -f "$LAST_TS_FILE" ]; then
        echo "$start_ts" > "$LAST_TS_FILE"
    fi

    local last_ts
    last_ts=$(cat "$LAST_TS_FILE")
    echo "$end_ts" > "$LAST_TS_FILE"

    local resp
    resp=$(api_call "/log/?type=5&start_timestamp=${last_ts}&end_timestamp=${end_ts}&page=0&page_size=50")
    local http_code
    http_code=$(echo "$resp" | tail -1)
    local body
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        local msg="错误日志 API 返回 HTTP ${http_code}"
        err "$msg"
        send_wechat "错误日志 API 异常" "> ${msg}\n> 地址: /api/log?type=5"
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        warn "错误日志 API 异常: $(echo "$body" | jq -r '.message // "unknown"')"
        return 0
    fi

    local total
    total=$(echo "$body" | jq -r '.data.total // 0')
    if [ "$total" -eq 0 ]; then
        ok "无错误日志"
        return 0
    fi

    # 提取错误摘要
    local items
    items=$(echo "$body" | jq -r '.data.items[] | "- [\(.channel_name // "system")] \(.model_name // "") → \(.content[0:120])"' 2>/dev/null || echo "")
    local first_errors
    first_errors=$(echo "$items" | head -10)

    warn "发现 ${total} 条错误日志"
    send_wechat "发现 ${total} 条错误日志" "> 时间范围: $(date -d "@${last_ts}" '+%H:%M:%S') ~ $(date '+%H:%M:%S')\n${first_errors}\n\n> 共 **${total}** 条错误"
    return 1
}

# ---- 检查 3: 渠道报错 ----
check_channel_errors() {
    log "${CYAN}[检查3] 渠道报错分析...${NC}"

    local now_ms end_ts start_ts
    now_ms=$(now_ts_ms)
    end_ts=$((now_ms / 1000))
    start_ts=$((end_ts - 300))

    local channels_to_check="${MONITOR_CHANNELS}"

    # 如果没有指定渠道，先查询最近有错误的渠道列表
    local resp
    resp=$(api_call "/log/?type=5&start_timestamp=${start_ts}&end_timestamp=${end_ts}&page=0&page_size=200")
    local http_code
    http_code=$(echo "$resp" | tail -1)
    local body
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        local msg="渠道报错 API 返回 HTTP ${http_code}"
        err "$msg"
        send_wechat "渠道报错 API 异常" "> ${msg}\n> 地址: /api/log?type=5"
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        warn "渠道报错 API 异常: $(echo "$body" | jq -r '.message // "unknown"')"
        return 0
    fi

    local total
    total=$(echo "$body" | jq -r '.data.total // 0')
    if [ "$total" -eq 0 ]; then
        ok "渠道无报错"
        return 0
    fi

    # 按渠道归类
    local channel_summary
    channel_summary=$(echo "$body" | jq -r '[.data.items[] | select(.channel != 0 and .channel_name != "")] | group_by(.channel_name) | .[] | "\(.[0].channel_name): \(length) 次 | 模型: \([.[].model_name] | unique | join(", "))"' 2>/dev/null || echo "")

    if [ -n "$channel_summary" ]; then
        warn "渠道报错汇总:"
        echo "$channel_summary" | while IFS= read -r line; do
            log "  ${RED}→${NC} $line"
        done
        send_wechat "渠道报错汇总" "> 最近5分钟各渠道错误:\n$(echo "$channel_summary" | sed 's/^/> /')\n\n> 共计 ${total} 条错误"
    fi
    return 1
}

# ---- 检查 4: 额度/计费异常 ----
check_quota_anomaly() {
    log "${CYAN}[检查4] 额度消耗统计...${NC}"

    local now_ms end_ts start_ts
    now_ms=$(now_ts_ms)
    end_ts=$((now_ms / 1000))
    start_ts=$((end_ts - 300))

    local resp
    resp=$(api_call "/log/stat?type=2&start_timestamp=${start_ts}&end_timestamp=${end_ts}")
    local http_code
    http_code=$(echo "$resp" | tail -1)
    local body
    body=$(echo "$resp" | sed '$d')

    if [ "$http_code" != "200" ]; then
        local msg="额度统计 API 返回 HTTP ${http_code}"
        err "$msg"
        send_wechat "额度统计 API 异常" "> ${msg}\n> 地址: /api/log/stat?type=2"
        return 1
    fi

    local success
    success=$(echo "$body" | jq -r '.success // false')
    if [ "$success" != "true" ]; then
        warn "额度统计 API 异常: $(echo "$body" | jq -r '.message // "unknown"')"
        return 0
    fi

    local quota rpm tpm
    quota=$(echo "$body" | jq -r '.data.quota // 0')
    rpm=$(echo "$body" | jq -r '.data.rpm // 0')
    tpm=$(echo "$body" | jq -r '.data.tpm // 0')

    # 读取历史状态
    local prev_quota=0 prev_rpm=0 prev_tpm=0
    if [ -f "$STATE_FILE" ]; then
        prev_quota=$(grep "^quota=" "$STATE_FILE" 2>/dev/null | cut -d'=' -f2 || echo 0)
        prev_rpm=$(grep "^rpm=" "$STATE_FILE" 2>/dev/null | cut -d'=' -f2 || echo 0)
        prev_tpm=$(grep "^tpm=" "$STATE_FILE" 2>/dev/null | cut -d'=' -f2 || echo 0)
    fi

    # 保存当前状态
    echo "quota=$quota" > "$STATE_FILE"
    echo "rpm=$rpm" >> "$STATE_FILE"
    echo "tpm=$tpm" >> "$STATE_FILE"

    local quota_diff=$((quota - prev_quota))
    if [ "$prev_quota" -gt 0 ]; then
        local pct=$(( quota_diff * 100 / prev_quota ))
    else
        local pct=0
    fi

    ok "5分钟内消耗: quota=${quota}, rpm=${rpm}, tpm=${tpm}"

    # 额度异常告警
    if [ "${QUOTA_THRESHOLD:-0}" -gt 0 ] && [ "$quota_diff" -gt "$QUOTA_THRESHOLD" ]; then
        warn "额度消耗异常: 5分钟内消耗 ${quota_diff} (阈值: ${QUOTA_THRESHOLD})"
        send_wechat "额度消耗异常" "> 5分钟内消耗: **${quota_diff}**\n> 阈值: ${QUOTA_THRESHOLD}\n> 当前 RPM: ${rpm} | TPM: ${tpm}"
        return 1
    fi

    return 0
}

# ---- 主流程 ----
main() {
    log ""
    log "======== $(date '+%Y-%m-%d %H:%M:%S') ========"
    log "目标: ${API_URL}"

    local errors=0

    check_service_alive || ((errors++))

    # 只有服务存活时才继续检查
    if [ "$errors" -eq 0 ]; then
        check_error_logs || ((errors++))
        check_channel_errors || ((errors++))
        check_quota_anomaly || ((errors++))
    fi

    log ""
    if [ "$errors" -eq 0 ]; then
        ok "全部检查通过"
    else
        warn "发现 ${errors} 项异常"
    fi
    log "=========================================="
}

main

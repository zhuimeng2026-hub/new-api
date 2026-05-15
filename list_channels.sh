#!/bin/bash
# 查询 aikey.aixifs.com 渠道列表

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 读取配置
API_URL=$(grep "^new_api_url=" .env | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
API_KEY=$(grep "^new_api_key=" .env | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')

API_URL="${API_URL:-https://aikey.aixifs.com/}"

echo "==================================="
echo "渠道查询"
echo "  API URL: $API_URL"
echo "  API Key: ${API_KEY:0:20}..."
echo "==================================="
echo

# 1. 查询渠道列表
echo -e "${CYAN}[1] 查询渠道列表...${NC}"
CHANNELS_RESPONSE=$(curl -s "${API_URL}api/channel/" \n    -H "Authorization: Bearer $API_KEY" \n    -H "New-Api-User: 1" \n    -H "Content-Type: application/json" 2>/dev/null)

if [[ "$CHANNELS_RESPONSE" == *"error"* ]] || [[ -z "$CHANNELS_RESPONSE" ]]; then
    echo -e "${RED}查询失败${NC}"
    echo "$CHANNELS_RESPONSE" | jq -r '.error.message // .' 2>/dev/null || echo "$CHANNELS_RESPONSE"
    exit 1
fi

# 获取总数
TOTAL=$(echo "$CHANNELS_RESPONSE" | jq -r '.data.total // length' 2>/dev/null)
echo -e "找到 ${GREEN}$TOTAL${NC} 个渠道"
echo

# 格式化输出
echo -e "${BLUE}渠道列表:${NC}"
echo "--------------------------------------------------------------------------------"
printf "%-5s %-30s %-20s %-15s %-10s %-20s\n" "ID" "名称" "类型" "状态" "优先级" "测试模型"
echo "--------------------------------------------------------------------------------"

# 渠道类型映射
declare -A TYPE_NAMES=(
    [1]="OpenAI"
    [14]="Anthropic"
    [17]="通义千问"
    [26]="智谱BigModel"
    [35]="MiniMax"
)

echo "$CHANNELS_RESPONSE" | jq -r '.data.items[]? | "\(.id // "N/A")|\(.name // "N/A")|\(.type // "N/A")|\(.status // "unknown")|\(.priority // 0)|\(.test_model // "-")"' 2>/dev/null | \nwhile IFS='|' read -r id name type status priority test_model; do
    # 格式化状态
    case "$status" in
        1|true|enabled|active) status_str="${GREEN}启用${NC}" ;;
        2|pending) status_str="${YELLOW}测试中${NC}" ;;
        0|false|disabled|inactive) status_str="${RED}禁用${NC}" ;;
        *) status_str="${YELLOW}$status${NC}" ;;
    esac
    # 类型名称
    type_name="${TYPE_NAMES[$type]:-Unknown($type)}"
    # 截断过长的名称和模型名
    name=$(echo "$name" | cut -c1-28)
    test_model=$(echo "$test_model" | cut -c1-18)
    printf "%-5s %-30s %-20s %-15s %-10s %-20s\n" "$id" "$name" "$type_name" "$status_str" "$priority" "$test_model"
done

echo "--------------------------------------------------------------------------------"
echo

# 2. 按渠道类型统计
echo -e "${CYAN}[2] 渠道类型统计:${NC}"
echo "$CHANNELS_RESPONSE" | jq -r '.data.type_counts | to_entries[] | "\(.key): \(.value) 个"' 2>/dev/null
echo

# 3. 按状态统计
echo -e "${CYAN}[3] 渠道状态统计:${NC}"
ENABLED=$(echo "$CHANNELS_RESPONSE" | jq '[.data.items[]? | select(.status == 1)] | length' 2>/dev/null)
DISABLED=$(echo "$CHANNELS_RESPONSE" | jq '[.data.items[]? | select(.status == 0)] | length' 2>/dev/null)
TESTING=$(echo "$CHANNELS_RESPONSE" | jq '[.data.items[]? | select(.status == 2)] | length' 2>/dev/null)

echo -e "  ${GREEN}启用: $ENABLED${NC}"
echo -e "  ${RED}禁用: $DISABLED${NC}"
echo -e "  ${YELLOW}测试中: $TESTING${NC}"
echo

# 4. 显示模型列表（所有模型）
echo -e "${CYAN}[4] 所有可用模型:${NC}"
echo "$CHANNELS_RESPONSE" | jq -r '.data.items[]? | .models // empty' 2>/dev/null | tr ',' '\n' | sort -u | nl -w2 -s'. '
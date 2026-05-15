#!/bin/bash
# 测试 aikey.aixifs.com 渠道模型可用性

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 读取 .env 文件
ENV_FILE=".env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}错误: 找不到 .env 文件${NC}"
    exit 1
fi

API_URL=$(grep "^new_api_url=" .env | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
API_KEY=$(grep "^new_api_llm_key=" .env | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')

# 默认值
API_URL="${API_URL:-https://aikey.aixifs.com/}"

# 如果传入第一个参数是 key 名称，使用指定的 key
if [[ "$1" == "new_api_key" ]]; then
    API_KEY=$(grep "^new_api_key=" .env | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
    shift
elif [[ "$1" == "scnet_key" ]]; then
    API_KEY=$(grep "^scnet_key=" .env | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
    API_URL=$(grep "^scnet_url=" .env | cut -d'=' -f2- | tr -d '\r' | sed 's/^"//;s/"$//')
    shift
fi

if [[ -z "$API_KEY" ]]; then
    echo -e "${RED}错误: 未找到 API key${NC}"
    exit 1
fi

echo "==================================="
echo "测试配置:"
echo "  API URL: $API_URL"
echo "  API Key: ${API_KEY:0:20}..."
echo "==================================="
echo

# 测试用的简单提示词
TEST_PROMPT="Say hello"

# 获取模型列表
echo "获取模型列表..."
MODEL_RESPONSE=$(curl -s "${API_URL}v1/models" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json")

if [[ "$MODEL_RESPONSE" == *"error"* ]]; then
    echo -e "${RED}获取模型列表失败:${NC}"
    echo "$MODEL_RESPONSE" | jq -r '.error.message // .error' 2>/dev/null || echo "$MODEL_RESPONSE"
    exit 1
fi

# 提取模型列表
MODELS=$(echo "$MODEL_RESPONSE" | jq -r '.data[].id' 2>/dev/null)

if [[ -z "$MODELS" ]]; then
    echo -e "${RED}未找到任何模型${NC}"
    exit 1
fi

MODEL_COUNT=$(echo "$MODELS" | wc -l)
echo -e "找到 ${GREEN}$MODEL_COUNT${NC} 个模型"
echo

# 选择测试模型（可选：只测试部分模型以提高速度）
# 如果传入参数，使用指定模型；否则测试前10个
if [[ -n "$1" ]]; then
    TEST_MODELS="$1"
else
    echo "默认测试前10个模型（传入参数可测试指定模型）"
    echo
    TEST_MODELS=$(echo "$MODELS" | head -10)
fi

echo "开始测试..."
echo "----------------------------------------"

SUCCESS_COUNT=0
FAIL_COUNT=0
TOTAL_COUNT=0

# 测试函数
test_model() {
    local model=$1
    local start_time=$(date +%s)

    response=$(curl -s -w "\n%{http_code}" \
        -X POST "${API_URL}v1/chat/completions" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$model\",
            \"messages\": [{\"role\": \"user\", \"content\": \"Hi\"}],
            \"max_tokens\": 10,
            \"stream\": false
        }" 2>/dev/null)

    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [[ "$http_code" == "200" ]]; then
        content=$(echo "$body" | jq -r '.choices[0].message.content // "无内容"' 2>/dev/null)
        echo -e "${GREEN}✓${NC} $model (${duration}s) - $content"
        return 0
    else
        error_msg=$(echo "$body" | jq -r '.error.message // "未知错误"' 2>/dev/null)
        echo -e "${RED}✗${NC} $model (HTTP $http_code) - $error_msg"
        return 1
    fi
}

# 串行测试（更稳定）
for model in $TEST_MODELS; do
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    if test_model "$model"; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    # 避免速率限制
    sleep 0.5
done

echo "----------------------------------------"
echo -e "测试完成: ${GREEN}成功 $SUCCESS_COUNT${NC} / ${RED}失败 $FAIL_COUNT${NC} / 总计 $TOTAL_COUNT"

# 退出码
if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
else
    exit 0
fi

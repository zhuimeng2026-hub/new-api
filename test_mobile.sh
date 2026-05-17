#!/bin/bash
# 测试中国移动大模型渠道 (MiniMax-M2.5)
# 通过 newapi 网关调用，模型映射: MiniMax-M2.5 -> minimax-m25

source <(grep -E '^(new_api_url|new_api_llm_key)=' /opt/new-api/.env)

MODEL="MiniMax-M2.5"
URL="${new_api_url}v1/chat/completions"
KEY="${new_api_llm_key}"

echo "=== 中国移动 MiniMax-M2.5 测试 ==="
echo "网关: ${new_api_url}"
echo "模型: ${MODEL}"
echo

# 1. 普通请求
echo "--- 测试1: 普通请求 ---"
START=$(date +%s%N)
RESP=$(curl -s -w "\n%{http_code} %{time_total}" "$URL" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$MODEL\",
    \"messages\": [{\"role\": \"user\", \"content\": \"你好，请用一句话介绍自己\"}],
    \"max_tokens\": 1024
  }")
HTTP_CODE=$(echo "$RESP" | tail -1 | awk '{print $1}')
TIME=$(echo "$RESP" | tail -1 | awk '{print $2}')
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    CONTENT=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])" 2>/dev/null)
    USAGE=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); u=d.get('usage',{}); print(f'输入:{u.get(\"prompt_tokens\",\"?\")} 输出:{u.get(\"completion_tokens\",\"?\")} 总计:{u.get(\"total_tokens\",\"?\")}')" 2>/dev/null)
    echo "状态: ${HTTP_CODE}  耗时: ${TIME}s"
    echo "回复: ${CONTENT}"
    echo "用量: ${USAGE}"
else
    echo "状态: ${HTTP_CODE}  耗时: ${TIME}s"
    echo "错误: $(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error',{}).get('message', d.get('message','未知错误')))" 2>/dev/null || echo "$BODY" | head -c 200)"
fi
echo

# 2. 流式请求
echo "--- 测试2: 流式请求 ---"
START=$(date +%s%N)
STREAM_RESP=$(curl -s --max-time 30 "$URL" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$MODEL\",
    \"messages\": [{\"role\": \"user\", \"content\": \"用三个词形容人工智能\"}],
    \"max_tokens\": 512,
    \"stream\": true
  }")
END=$(date +%s%N)
ELAPSED=$(( (END - START) / 1000000 ))

CHUNK_COUNT=$(echo "$STREAM_RESP" | grep -c '^data: ')
HAS_DONE=$(echo "$STREAM_RESP" | grep -c 'data: \[DONE\]')
STREAM_TEXT=$(echo "$STREAM_RESP" | grep '^data: ' | grep -v '\[DONE\]' | python3 -c "
import json, sys
text = ''
for line in sys.stdin:
    line = line.strip()
    if not line or line == 'data: [DONE]':
        continue
    try:
        d = json.loads(line[5:])
        delta = d['choices'][0].get('delta', {})
        text += delta.get('content', '')
    except:
        pass
print(text)
" 2>/dev/null)

if [ "$CHUNK_COUNT" -gt 0 ]; then
    echo "状态: 流式成功  耗时: ${ELAPSED}ms  数据块: ${CHUNK_COUNT}"
    echo "回复: ${STREAM_TEXT}"
else
    echo "状态: 流式失败"
    echo "响应: $(echo "$STREAM_RESP" | head -c 300)"
fi
echo

# 3. 直连测试 (绕过网关)
echo "--- 测试3: 直连中国移动 API ---"
MOBILE_URL=$(grep 'mobile_url=' /opt/new-api/.env | head -1 | cut -d= -f2)
MOBILE_KEY=$(grep 'mobile_key=' /opt/new-api/.env | head -1 | cut -d= -f2)

START=$(date +%s%N)
DIRECT_RESP=$(curl -s -w "\n%{http_code} %{time_total}" "$MOBILE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $MOBILE_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"minimax-m25\",
    \"messages\": [{\"role\": \"user\", \"content\": \"1+1=?\"}],
    \"max_tokens\": 50
  }")
HTTP_CODE=$(echo "$DIRECT_RESP" | tail -1 | awk '{print $1}')
TIME=$(echo "$DIRECT_RESP" | tail -1 | awk '{print $2}')
BODY=$(echo "$DIRECT_RESP" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    CONTENT=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])" 2>/dev/null)
    echo "状态: ${HTTP_CODE}  耗时: ${TIME}s"
    echo "回复: ${CONTENT}"
else
    echo "状态: ${HTTP_CODE}  耗时: ${TIME}s"
    echo "响应: $(echo "$BODY" | head -c 300)"
fi

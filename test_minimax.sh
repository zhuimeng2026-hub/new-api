#!/bin/bash
KEY="sk-sp-ODQwLTExMzU4MTM4MTAzLTE3Nzc0NDAzODAzOTE="
URL="https://api.scnet.cn/api/llm/v1/chat/completions"

echo "=== Test MiniMax-M2.5 ==="
curl -s -w "\nHTTP: %{http_code}" --connect-timeout 10 --max-time 60 \
  -H "Authorization: Bearer ${KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MiniMax-M2.5",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 10
  }' \
  "$URL"
echo ""

echo ""
echo "=== Test Qwen3-235B-A22B (reference) ==="
curl -s -w "\nHTTP: %{http_code}" --connect-timeout 10 --max-time 60 \
  -H "Authorization: Bearer ${KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-235B-A22B",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 10
  }' \
  "$URL"
echo ""

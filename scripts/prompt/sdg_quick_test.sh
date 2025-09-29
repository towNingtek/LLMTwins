#!/bin/bash

# SDG Chat Demo 快速測試腳本
# 用於快速驗證 API 是否正常運作

HOST="http://localhost:8002"
ENDPOINT="/api/chat_demo"

echo "=== SDG Chat Demo 快速測試 ==="

# 簡單測試
curl -sS -N --http1.1 --no-buffer "${HOST}${ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -d '{
    "sdgs": "1,3",
    "model": "qwen2.5:7b-instruct",
    "stream": true,
    "userMessage": "如何改善社區健康與貧窮問題？"
  }'

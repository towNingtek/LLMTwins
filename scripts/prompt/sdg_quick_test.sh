#!/bin/bash

# SDG Chat planning 快速測試腳本
# 用於快速驗證 API 是否正常運作

HOST="http://localhost:8002"
ENDPOINT="/api/planning"

echo "=== SDG Chat planning 快速測試 ==="

# 簡單測試
curl -sS -N --http1.1 --no-buffer "${HOST}${ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -d '{
    "sdgs": "1,3",
    "model": "openai/gpt-4o-mini",
    "stream": true,
    "userMessage": "如何改善社區健康與貧窮問題？"
  }'

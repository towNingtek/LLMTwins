#!/bin/bash

# SDG Chat planning 非串流測試腳本
# 測試 stream: false 模式

HOST="http://localhost:8002"
ENDPOINT="/api/planning"

echo "=== SDG Chat planning 非串流測試 ==="

curl -sS "${HOST}${ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -d '{
    "sdgs": "1,2,3",
    "model": "openai/gpt-4o-mini",
    "stream": false,
    "userMessage": "計劃名稱：三農政策整合計畫\n用戶詢問：如何整合消除貧窮、零飢餓和健康福祉的政策？"
  }' | jq .

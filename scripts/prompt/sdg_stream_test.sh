#!/bin/bash

# SDG Chat Demo 串流測試腳本
# 測試 /api/chat_demo 端點的串流功能

HOST="http://localhost:8002"
ENDPOINT="/api/chat_demo"

echo "=== SDG Chat Demo 串流測試 ==="
echo "測試端點: ${HOST}${ENDPOINT}"
echo

# 測試案例1: 指定單一 SDG
echo "【測試案例1】指定 SDG 1 (消除貧窮)"
curl -sS -N --http1.1 --no-buffer "${HOST}${ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -d '{
    "sdgs": "1",
    "model": "qwen2.5:7b-instruct",
    "stream": true,
    "userMessage": "計劃名稱：城鄉發展計畫\n用戶詢問：如何透過SDG1來改善偏鄉貧窮問題？"
  }'

echo -e "\n\n==========================================\n"

# 測試案例2: 指定多個 SDG
echo "【測試案例2】指定 SDG 3,4,8 (健康、教育、就業)"
curl -sS -N --http1.1 --no-buffer "${HOST}${ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -d '{
    "sdgs": "3,4,8",
    "model": "qwen2.5:7b-instruct", 
    "stream": true,
    "userMessage": "計劃名稱：青年就業促進計畫\n用戶詢問：如何整合健康、教育和就業政策來幫助青年發展？"
  }'

echo -e "\n\n==========================================\n"

# 測試案例3: SDG 格式變化測試
echo "【測試案例3】不同 SDG 格式測試 (sdg11, sdg13)"
curl -sS -N --http1.1 --no-buffer "${HOST}${ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -d '{
    "sdgs": "sdg11,sdg13",
    "model": "qwen2.5:7b-instruct",
    "stream": true,
    "userMessage": "永續城市發展如何結合氣候行動？"
  }'

echo -e "\n\n==========================================\n"

# 測試案例4: 無指定 SDG (隨機選擇)
echo "【測試案例4】無指定 SDG，系統隨機選擇"
curl -sS -N --http1.1 --no-buffer "${HOST}${ENDPOINT}" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2.5:7b-instruct",
    "stream": true,
    "userMessage": "請分析永續發展相關政策建議"
  }'

echo -e "\n\n測試完成!"

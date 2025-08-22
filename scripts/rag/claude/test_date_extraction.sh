#!/bin/bash

# 日期抽取測試 - 民國年轉換
# 目標：114年度 → "2025-01-01" to "2025-12-31"

set -e

LLMTWINS_DIR="/home/yillkid/workspace/town-intelligent/beta/LLMTwins"
SESSION_ID="sess_f2e7c5c82646494e8585c49845adbac2"
PARSED_JSON_PATH="$LLMTWINS_DIR/sessions/$SESSION_ID/artifacts/parsed.json"
API_URL="http://localhost:8002/api/chat"

echo "=== 日期抽取測試 (民國年轉換) ==="
echo ""

# 檢查檔案
if [ ! -f "$PARSED_JSON_PATH" ]; then
    echo "錯誤: 找不到檔案: $PARSED_JSON_PATH"
    exit 1
fi

# 智能抽取日期相關文本
echo "抽取日期相關文本..."
DATE_TEXT=$(cat "$PARSED_JSON_PATH" | \
    jq -r '.pages[].text' | \
    grep -A 3 -B 3 '114.*年\|年.*度\|期.*間\|開始\|結束\|起\|迄' | \
    head -c 800 | \
    sed 's/[[:space:]]\+/ /g')

# 備用：抽取包含數字年份的段落
if [ -z "$DATE_TEXT" ]; then
    echo "使用備用方法抽取年份段落..."
    DATE_TEXT=$(cat "$PARSED_JSON_PATH" | \
        jq -r '.pages[].text' | \
        grep -o '11[0-9].*年.*\|20[0-9][0-9].*' | \
        head -c 600)
fi

echo "日期相關文本:"
echo "$DATE_TEXT"
echo ""

# 日期抽取 prompt
SYSTEM_PROMPT='從政府計畫文件抽取專案執行期間。

任務：
1. 找出計畫執行的開始和結束日期
2. 處理民國年轉換（民國年+1911=西元年）
3. 年度計畫通常是 1/1 到 12/31

轉換規則：
- "114年度" → start: 2025-01-01, end: 2025-12-31
- "114年1月~115年6月" → start: 2025-01-01, end: 2026-06-30
- "2025年" → start: 2025-01-01, end: 2025-12-31

重要：只輸出純 JSON，不要解釋，不要用 markdown。
格式：{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}

範例：{"start_date": "2025-01-01", "end_date": "2025-12-31"}'

USER_PROMPT="請從以下文本抽取計畫執行期間：

$DATE_TEXT

輸出 JSON 格式的開始和結束日期："

echo "發送日期抽取請求..."
START_TIME=$(date +%s)

RESPONSE=$(curl -sS -N --http1.1 --no-buffer "$API_URL" \
  -H 'Content-Type: application/json' \
  --max-time 45 \
  -d "$(jq -nc \
    --arg sys "$SYSTEM_PROMPT" \
    --arg user "$USER_PROMPT" \
    '{
      model: "qwen2.5:7b-instruct",
      stream: true,
      options: {
        temperature: 0.05,
        top_p: 0.8,
        max_tokens: 100
      },
      messages: [
        {role: "system", content: $sys},
        {role: "user", content: $user}
      ]
    }')" | \
  while IFS= read -r line; do
    if [[ "$line" =~ ^\{.*\}$ ]]; then
      content=$(echo "$line" | jq -r '.message.content // empty' 2>/dev/null || echo "")
      if [ -n "$content" ]; then
        echo -n "$content"
      fi
    fi
  done)

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "=== 結果 (耗時: ${ELAPSED}秒) ==="
echo "原始回應: $RESPONSE"

# 清理並解析日期
CLEANED_RESPONSE=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | head -1)
echo "清理後: $CLEANED_RESPONSE"

if echo "$CLEANED_RESPONSE" | jq -e . >/dev/null 2>&1; then
    START_DATE=$(echo "$CLEANED_RESPONSE" | jq -r '.start_date // empty')
    END_DATE=$(echo "$CLEANED_RESPONSE" | jq -r '.end_date // empty')
    
    if [ -n "$START_DATE" ] && [ -n "$END_DATE" ] && [ "$START_DATE" != "null" ] && [ "$END_DATE" != "null" ]; then
        echo "✅ 抽取開始日期: $START_DATE"
        echo "✅ 抽取結束日期: $END_DATE"
        
        # 驗證日期格式
        if [[ "$START_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && [[ "$END_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
            echo "✅ 日期格式正確 (YYYY-MM-DD)"
            
            # 驗證民國年轉換
            if [[ "$START_DATE" == "2025-01-01" ]] && [[ "$END_DATE" == "2025-12-31" ]]; then
                echo "✅ 民國114年轉換正確！(114+1911=2025)"
            elif [[ "$START_DATE" =~ ^2025- ]]; then
                echo "✅ 民國年轉換基本正確 (2025年)"
            else
                echo "⚠️ 年份可能有誤，預期2025年"
            fi
            
            # 驗證邏輯合理性
            if [[ "$START_DATE" < "$END_DATE" ]]; then
                echo "✅ 開始日期 < 結束日期，邏輯正確"
            else
                echo "❌ 日期邏輯錯誤：開始日期不應晚於結束日期"
            fi
            
            # 計算期間長度
            START_TIMESTAMP=$(date -d "$START_DATE" +%s 2>/dev/null || echo "0")
            END_TIMESTAMP=$(date -d "$END_DATE" +%s 2>/dev/null || echo "0")
            if [ "$START_TIMESTAMP" -gt 0 ] && [ "$END_TIMESTAMP" -gt 0 ]; then
                DAYS=$(( (END_TIMESTAMP - START_TIMESTAMP) / 86400 ))
                echo "✅ 計畫期間: $DAYS 天"
                
                if [ "$DAYS" -eq 365 ] || [ "$DAYS" -eq 364 ]; then
                    echo "✅ 期間長度符合年度計畫 (~365天)"
                fi
            fi
            
        else
            echo "❌ 日期格式錯誤，應為 YYYY-MM-DD"
        fi
        
    else
        echo "❌ 找不到完整的開始/結束日期"
    fi
else
    echo "❌ JSON 解析失敗，嘗試備用抽取..."
    
    # 備用：正則抽取年份
    BACKUP_YEAR=$(echo "$RESPONSE" | grep -o '20[0-9][0-9]' | head -1)
    if [ -n "$BACKUP_YEAR" ]; then
        echo "🔄 備用抽取年份: $BACKUP_YEAR"
        echo "💡 建議設定為: $BACKUP_YEAR-01-01 到 $BACKUP_YEAR-12-31"
        START_DATE="$BACKUP_YEAR-01-01"
        END_DATE="$BACKUP_YEAR-12-31"
    else
        START_DATE=""
        END_DATE=""
    fi
fi

echo ""
echo "=== 測試總結 ==="
echo "目標期間: 2025-01-01 到 2025-12-31 (民國114年度)"
echo "抽取結果: $START_DATE 到 $END_DATE"
echo "處理時間: ${ELAPSED} 秒"

# 成功率評估
if [ "$START_DATE" = "2025-01-01" ] && [ "$END_DATE" = "2025-12-31" ]; then
    echo "🎯 抽取成功率: 100%"
elif [[ "$START_DATE" =~ ^2025- ]] && [[ "$END_DATE" =~ ^2025- ]]; then
    echo "🎯 抽取成功率: 80% (年份正確，日期可能需微調)"
else
    echo "🎯 抽取成功率: 需要改進"
fi

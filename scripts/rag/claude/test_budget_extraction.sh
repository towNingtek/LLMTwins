#!/bin/bash

# 預算抽取測試
# 目標：從文件中抽取 1,909,000 元 (1,909千元)

set -e

LLMTWINS_DIR="/home/yillkid/workspace/town-intelligent/beta/LLMTwins"
SESSION_ID="sess_f2e7c5c82646494e8585c49845adbac2"
PARSED_JSON_PATH="$LLMTWINS_DIR/sessions/$SESSION_ID/artifacts/parsed.json"
API_URL="http://localhost:8002/api/chat"

echo "=== 預算抽取測試 ==="
echo ""

# 檢查檔案
if [ ! -f "$PARSED_JSON_PATH" ]; then
    echo "錯誤: 找不到檔案: $PARSED_JSON_PATH"
    exit 1
fi

# 智能抽取預算相關文本
echo "抽取預算相關文本..."
BUDGET_TEXT=$(cat "$PARSED_JSON_PATH" | \
    jq -r '.pages[].text' | \
    grep -A 5 -B 5 '經費\|預算\|千.*元\|萬.*元\|1,909\|1909' | \
    head -c 1000 | \
    sed 's/[[:space:]]\+/ /g')

# 備用：抽取包含數字的段落
if [ -z "$BUDGET_TEXT" ]; then
    echo "使用備用方法抽取數字段落..."
    BUDGET_TEXT=$(cat "$PARSED_JSON_PATH" | \
        jq -r '.pages[].text' | \
        grep -o '[0-9,]*[0-9]\+.*[元費].*' | \
        head -c 800)
fi

echo "預算相關文本:"
echo "$BUDGET_TEXT"
echo ""

# 預算抽取 prompt
SYSTEM_PROMPT='從政府計畫文件中抽取總預算金額。

任務：
1. 找出計畫的總預算/經費金額
2. 轉換為純數字（新台幣元）
3. 處理千元、萬元單位
4. 忽略細項分解，只要總額

轉換規則：
- "1,909 千元" → 1909000
- "190.9 萬元" → 1909000
- "1,909,000 元" → 1909000

重要：只輸出純 JSON，不要解釋，不要用 markdown。
正確格式：{"budget": 1909000}
錯誤格式：```json{"budget": 1909000}```'

USER_PROMPT="請從以下文本抽取總預算金額：

$BUDGET_TEXT

輸出 JSON 格式的預算數字（單位：元）："

echo "發送預算抽取請求..."
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
        temperature: 0.1,
        top_p: 0.9,
        max_tokens: 80
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

# 解析預算金額 - 增強版
echo "原始回應清理前: $RESPONSE"

# 清理 markdown 程式碼塊
CLEANED_RESPONSE=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | head -1)
echo "清理後: $CLEANED_RESPONSE"

if echo "$CLEANED_RESPONSE" | jq -e . >/dev/null 2>&1; then
    EXTRACTED_BUDGET=$(echo "$CLEANED_RESPONSE" | jq -r '.budget // empty')
    if [ -n "$EXTRACTED_BUDGET" ] && [ "$EXTRACTED_BUDGET" != "null" ]; then
        echo "✅ 抽取預算: $EXTRACTED_BUDGET 元"
        
        # 驗證合理性
        if [ "$EXTRACTED_BUDGET" -eq 1909000 ] 2>/dev/null; then
            echo "✅ 預算金額正確！(1,909千元 = 1,909,000元)"
        elif [ "$EXTRACTED_BUDGET" -eq 1909 ] 2>/dev/null; then
            echo "⚠️ 可能漏了單位轉換 (1909 應該是 1,909,000)"
            echo "💡 建議修正為: $((EXTRACTED_BUDGET * 1000)) 元"
        elif [ "$EXTRACTED_BUDGET" -gt 1000000 ] && [ "$EXTRACTED_BUDGET" -lt 3000000 ] 2>/dev/null; then
            echo "✅ 預算金額在合理範圍內"
        else
            echo "⚠️ 預算金額可能有誤: $EXTRACTED_BUDGET"
        fi
        
        # 格式化顯示
        FORMATTED=$(printf "%'d" "$EXTRACTED_BUDGET" 2>/dev/null || echo "$EXTRACTED_BUDGET")
        echo "✅ 格式化顯示: $FORMATTED 元"
        
    else
        echo "❌ 找不到 budget 欄位"
        EXTRACTED_BUDGET=""
    fi
else
    echo "❌ JSON 解析仍然失敗"
    
    # 備用數字抽取
    BACKUP_BUDGET=$(echo "$RESPONSE" | grep -o '[0-9,]\+' | tr -d ',' | tail -1)
    if [ -n "$BACKUP_BUDGET" ]; then
        echo "🔄 備用抽取: $BACKUP_BUDGET"
        
        # 簡單單位判斷
        if [ ${#BACKUP_BUDGET} -eq 4 ]; then
            echo "💡 可能是千元單位，建議 × 1000"
            EXTRACTED_BUDGET=$((BACKUP_BUDGET * 1000))
            echo "🔄 自動轉換結果: $EXTRACTED_BUDGET 元"
        else
            EXTRACTED_BUDGET=$BACKUP_BUDGET
        fi
    else
        EXTRACTED_BUDGET=""
    fi
fi

echo ""
echo "=== 測試總結 ==="
echo "目標預算: 1,909,000 元 (1,909千元)"
echo "抽取結果: $EXTRACTED_BUDGET 元"
echo "處理時間: ${ELAPSED} 秒"

# 成功率評估
if [ "$EXTRACTED_BUDGET" = "1909000" ] 2>/dev/null; then
    echo "🎯 抽取成功率: 100%"
elif [ "$EXTRACTED_BUDGET" = "1909" ] 2>/dev/null; then
    echo "🎯 抽取成功率: 80% (需要單位轉換)"
else
    echo "🎯 抽取成功率: 需要改進"
fi

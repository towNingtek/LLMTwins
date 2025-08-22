#!/bin/bash

# 優化版標題抽取測試
# 重點：縮短文本、精確定位、加速處理

set -e

LLMTWINS_DIR="/home/yillkid/workspace/town-intelligent/beta/LLMTwins"
SESSION_ID="sess_f2e7c5c82646494e8585c49845adbac2"
PARSED_JSON_PATH="$LLMTWINS_DIR/sessions/$SESSION_ID/artifacts/parsed.json"
API_URL="http://localhost:8002/api/chat"

echo "=== 優化版標題抽取測試 ==="
echo ""

# 檢查檔案
if [ ! -f "$PARSED_JSON_PATH" ]; then
    echo "錯誤: 找不到檔案: $PARSED_JSON_PATH"
    exit 1
fi

# 聰明抽取：只取第一頁前 800 字元，並清理 OCR 雜訊
echo "智能抽取標題相關文本..."
TITLE_TEXT=$(cat "$PARSED_JSON_PATH" | \
    jq -r '.pages[0].text' | \
    head -c 800 | \
    sed 's/[[:space:]]\+/ /g' | \
    grep -o '計.*畫.*\|.*計 畫.*\|.*事 務.*計.*' | \
    head -5 | \
    tr '\n' ' ')

# 如果智能抽取失敗，回退到簡單方法
if [ -z "$TITLE_TEXT" ]; then
    echo "智能抽取失敗，使用備用方法..."
    TITLE_TEXT=$(cat "$PARSED_JSON_PATH" | jq -r '.pages[0].text' | head -c 500)
fi

echo "抽取到的關鍵文本:"
echo "$TITLE_TEXT"
echo ""

# 精簡 prompt
SYSTEM_PROMPT='從公文文件抽取計畫名稱。只輸出 JSON: {"name": "計畫名稱"}

規則：
1. 找出主要計畫名稱（通常在文件開頭）
2. 忽略「依據」、「設置要點」等細節
3. 移除「草案」等字樣
4. 保持 5-50 字長度'

USER_PROMPT="文件片段：$TITLE_TEXT

請抽取主要計畫名稱（JSON格式）："

echo "發送簡化請求..."
START_TIME=$(date +%s)

# 使用更快的設定
RESPONSE=$(curl -sS -N --http1.1 --no-buffer "$API_URL" \
  -H 'Content-Type: application/json' \
  --max-time 60 \
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

# 解析與評估
if echo "$RESPONSE" | jq -e . >/dev/null 2>&1; then
    EXTRACTED_NAME=$(echo "$RESPONSE" | jq -r '.name // empty')
    if [ -n "$EXTRACTED_NAME" ] && [ "$EXTRACTED_NAME" != "null" ]; then
        echo "✅ 抽取標題: $EXTRACTED_NAME"
        echo "✅ 長度: ${#EXTRACTED_NAME} 字元"
        echo "✅ 處理時間: ${ELAPSED} 秒"
        
        # 簡單驗證：是否為主計畫而非依據
        if echo "$EXTRACTED_NAME" | grep -q "設置要點\|依據\|辦法"; then
            echo "⚠️ 可能抽取到依據文件而非主計畫名稱"
        else
            echo "✅ 看起來是主計畫名稱"
        fi
        
        # 建議優化
        if [ ${#EXTRACTED_NAME} -gt 25 ]; then
            SHORT_NAME=$(echo "$EXTRACTED_NAME" | sed 's/委員會.*//g' | sed 's/設置.*//g')
            echo "💡 建議縮短為: $SHORT_NAME"
        fi
        
    else
        echo "❌ 找不到 name 欄位"
    fi
else
    echo "❌ JSON 解析失敗"
    echo "🔄 嘗試文本模式抽取..."
    
    # 正則抽取備案
    BACKUP_NAME=$(echo "$RESPONSE" | grep -o '[^"]*計畫[^"]*' | head -1 | sed 's/^[^a-zA-Z\u4e00-\u9fa5]*//g')
    if [ -n "$BACKUP_NAME" ]; then
        echo "🔄 備用結果: $BACKUP_NAME"
    fi
fi

echo ""
echo "=== 效能分析 ==="
echo "輸入文本長度: ${#TITLE_TEXT} 字元"
echo "處理時間: ${ELAPSED} 秒"
echo "速度: $((${#TITLE_TEXT} / ELAPSED)) 字元/秒"

# 如果太慢，給建議
if [ $ELAPSED -gt 30 ]; then
    echo ""
    echo "⚠️ 處理速度較慢，建議："
    echo "1. 檢查 GPU 可用性"
    echo "2. 考慮使用更小的模型（如 llama3:instruct）"
    echo "3. 進一步縮短輸入文本"
fi

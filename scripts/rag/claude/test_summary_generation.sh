#!/bin/bash

# 摘要生成測試 - 計畫理念 (philosophy)
# 目標：從文件生成 120-180 字的計畫理念摘要

set -e

LLMTWINS_DIR="/home/yillkid/workspace/town-intelligent/beta/LLMTwins"
SESSION_ID="sess_f2e7c5c82646494e8585c49845adbac2"
PARSED_JSON_PATH="$LLMTWINS_DIR/sessions/$SESSION_ID/artifacts/parsed.json"
API_URL="http://localhost:8002/api/chat"

echo "=== 摘要生成測試 (計畫理念) ==="
echo ""

# 檢查檔案
if [ ! -f "$PARSED_JSON_PATH" ]; then
    echo "錯誤: 找不到檔案: $PARSED_JSON_PATH"
    exit 1
fi

# 智能抽取計畫目的與內容相關文本
echo "抽取計畫目的與執行內容..."
SUMMARY_TEXT=$(cat "$PARSED_JSON_PATH" | \
    jq -r '.pages[].text' | \
    grep -A 10 -B 5 '目的\|目標\|效益\|計 畫.*內\|執行.*內容\|工作.*項目\|國 際.*事 務\|兩 岸.*事 務\|交 流.*活動' | \
    head -c 1500 | \
    sed 's/[[:space:]]\+/ /g')

# 備用：抽取第二頁的主要內容（通常包含計畫說明）
if [ ${#SUMMARY_TEXT} -lt 200 ]; then
    echo "使用備用方法抽取第二頁內容..."
    SUMMARY_TEXT=$(cat "$PARSED_JSON_PATH" | \
        jq -r '.pages[1].text // .pages[0].text' | \
        head -c 1200 | \
        sed 's/[[:space:]]\+/ /g')
fi

echo "計畫內容文本長度: ${#SUMMARY_TEXT} 字元"
echo "內容預覽:"
echo "$SUMMARY_TEXT" | head -c 300
echo "..."
echo ""

# 修正版 SYSTEM_PROMPT - 避免幻覺
SYSTEM_PROMPT='從政府計畫文件生成計畫理念摘要。

任務：
1. 仔細閱讀提供的計畫文件內容
2. 基於實際文件內容生成 120-180 字的計畫理念
3. 必須包含：計畫目標、執行方法、受益對象、預期效益
4. 使用正式但易懂的政府文件語調

重要要求：
- 必須基於提供的文件內容，不得編造內容
- 準確反映計畫的實際目標與方法
- 保持與原文件的一致性
- 字數控制在 120-180 字
- 分成 3-4 句完整表達

重要：只輸出純 JSON，不要解釋，不要用 markdown。
格式：{"philosophy": "計畫理念內容"}'

# 🔥 添加缺失的 USER_PROMPT
USER_PROMPT="請基於以下計畫文件，生成120-180字的計畫理念摘要：

計畫名稱：國際事務推動運用計畫
計畫內容：$SUMMARY_TEXT

要求：
1. 字數必須達到120-180字
2. 適當擴充執行方法與預期效益的描述
3. 可包含更多具體執行內容細節
4. 嚴格基於上述文件內容，不得編造無關內容

請生成詳細的計畫理念："

echo "發送摘要生成請求..."
START_TIME=$(date +%s)

# 降低創意性，提高準確性
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
        temperature: 0.2,
        top_p: 0.8,
        max_tokens: 400
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

# 清理並解析摘要
CLEANED_RESPONSE=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | head -1)
echo "清理後: $CLEANED_RESPONSE"

if echo "$CLEANED_RESPONSE" | jq -e . >/dev/null 2>&1; then
    EXTRACTED_PHILOSOPHY=$(echo "$CLEANED_RESPONSE" | jq -r '.philosophy // empty')
    
    if [ -n "$EXTRACTED_PHILOSOPHY" ] && [ "$EXTRACTED_PHILOSOPHY" != "null" ]; then
        echo ""
        echo "✅ 生成的計畫理念:"
        echo "「$EXTRACTED_PHILOSOPHY」"
        echo ""
        
        # 字數檢查
        CHAR_COUNT=${#EXTRACTED_PHILOSOPHY}
        echo "✅ 字數統計: $CHAR_COUNT 字元"
        
        if [ $CHAR_COUNT -ge 120 ] && [ $CHAR_COUNT -le 180 ]; then
            echo "✅ 字數符合要求 (120-180字)"
        elif [ $CHAR_COUNT -ge 100 ] && [ $CHAR_COUNT -le 200 ]; then
            echo "⚠️ 字數接近要求 (目前: $CHAR_COUNT, 目標: 120-180)"
        else
            echo "❌ 字數不符合要求 (目前: $CHAR_COUNT, 目標: 120-180)"
        fi
        
        # 內容品質檢查
        echo ""
        echo "=== 內容品質分析 ==="
        
        # 檢查關鍵詞
        if echo "$EXTRACTED_PHILOSOPHY" | grep -q "國際\|交流\|兩岸"; then
            echo "✅ 包含核心主題關鍵詞"
        else
            echo "⚠️ 可能缺少核心主題關鍵詞"
        fi
        
        if echo "$EXTRACTED_PHILOSOPHY" | grep -q "推動\|促進\|提升\|發展"; then
            echo "✅ 包含行動導向詞彙"
        else
            echo "⚠️ 可能缺少行動導向描述"
        fi
        
        if echo "$EXTRACTED_PHILOSOPHY" | grep -q "南投\|縣"; then
            echo "✅ 明確提及執行地區"
        else
            echo "⚠️ 可能缺少地區特色"
        fi
        
        # 句子結構分析
        SENTENCE_COUNT=$(echo "$EXTRACTED_PHILOSOPHY" | grep -o '。' | wc -l)
        echo "✅ 句子數量: $SENTENCE_COUNT 句"
        
        if [ $SENTENCE_COUNT -ge 3 ] && [ $SENTENCE_COUNT -le 6 ]; then
            echo "✅ 句子數量適中 (3-6句)"
        else
            echo "⚠️ 句子數量可能需要調整"
        fi
        
    else
        echo "❌ 找不到 philosophy 欄位"
        EXTRACTED_PHILOSOPHY=""
    fi
else
    echo "❌ JSON 解析失敗，嘗試備用抽取..."
    
    # 備用：直接從回應中抽取可能的摘要
    BACKUP_SUMMARY=$(echo "$RESPONSE" | sed 's/.*[:：]//' | head -c 200)
    if [ -n "$BACKUP_SUMMARY" ]; then
        echo "🔄 備用抽取摘要: $BACKUP_SUMMARY"
        EXTRACTED_PHILOSOPHY="$BACKUP_SUMMARY"
    else
        EXTRACTED_PHILOSOPHY=""
    fi
fi

echo ""
echo "=== 測試總結 ==="
echo "目標: 生成120-180字的計畫理念"
echo "實際字數: ${#EXTRACTED_PHILOSOPHY} 字元"
echo "處理時間: ${ELAPSED} 秒"

# 成功率評估
if [ -n "$EXTRACTED_PHILOSOPHY" ] && [ ${#EXTRACTED_PHILOSOPHY} -ge 120 ] && [ ${#EXTRACTED_PHILOSOPHY} -le 180 ]; then
    echo "🎯 生成成功率: 100%"
elif [ -n "$EXTRACTED_PHILOSOPHY" ] && [ ${#EXTRACTED_PHILOSOPHY} -ge 80 ]; then
    echo "🎯 生成成功率: 80% (內容合理，字數可能需微調)"
else
    echo "🎯 生成成功率: 需要改進"
fi

echo ""
echo "=== 建議 ==="
echo "如果要整合到 CMS，建議進一步檢查："
echo "1. 是否符合永續發展目標描述風格"
echo "2. 語調是否適合對外展示"
echo "3. 內容是否涵蓋關鍵利害關係人"

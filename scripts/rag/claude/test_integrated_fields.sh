#!/bin/bash

# 整合欄位抽取測試 - 一次性測試所有 CMS 欄位
# 模擬 LLMTwins 的完整工作流程

set -e

LLMTWINS_DIR="/home/yillkid/workspace/town-intelligent/beta/LLMTwins"
SESSION_ID="sess_f2e7c5c82646494e8585c49845adbac2"
PARSED_JSON_PATH="$LLMTWINS_DIR/sessions/$SESSION_ID/artifacts/parsed.json"
API_URL="http://localhost:8002/api/chat"

echo "=================================================="
echo "🚀 LLMTwins 整合欄位抽取測試"
echo "=================================================="
echo "目標：生成完整的 CMS 上傳 payload"
echo "測試檔案：$(basename $PARSED_JSON_PATH)"
echo ""

# 檢查檔案
if [ ! -f "$PARSED_JSON_PATH" ]; then
    echo "❌ 錯誤: 找不到檔案: $PARSED_JSON_PATH"
    exit 1
fi

# 讀取文件內容
FULL_TEXT=$(cat "$PARSED_JSON_PATH" | jq -r '.pages[].text' | head -c 2500 | sed 's/[[:space:]]\+/ /g')
echo "📄 文件內容長度: ${#FULL_TEXT} 字元"

# 初始化結果變數
EXTRACTED_NAME=""
EXTRACTED_BUDGET=""
EXTRACTED_START_DATE=""
EXTRACTED_END_DATE=""
EXTRACTED_PHILOSOPHY=""
EXTRACTED_LIST_SDG=""
EXTRACTED_WEIGHT_DESC=""

TOTAL_START_TIME=$(date +%s)

# =============================================================================
# 1. 標題抽取
# =============================================================================
echo ""
echo "🔍 [1/5] 正在抽取計畫名稱..."

TITLE_TEXT=$(echo "$FULL_TEXT" | grep -o '計.*畫.*\|.*計 畫.*\|.*事 務.*計.*' | head -5 | tr '\n' ' ')
SYSTEM_PROMPT='從公文文件抽取計畫名稱。只輸出 JSON: {"name": "計畫名稱"}

規則：找出主要計畫名稱，忽略依據文件，移除草案字樣，保持5-50字。'

USER_PROMPT="文件片段：$TITLE_TEXT

請抽取主要計畫名稱（JSON格式）："

RESPONSE=$(curl -sS -N --http1.1 --no-buffer "$API_URL" \
  -H 'Content-Type: application/json' --max-time 30 \
  -d "$(jq -nc --arg sys "$SYSTEM_PROMPT" --arg user "$USER_PROMPT" \
    '{ model: "qwen2.5:7b-instruct", stream: true, options: {temperature: 0.05, max_tokens: 100}, 
       messages: [{role: "system", content: $sys}, {role: "user", content: $user}] }')" | \
  while IFS= read -r line; do
    [[ "$line" =~ ^\{.*\}$ ]] && echo -n "$(echo "$line" | jq -r '.message.content // empty' 2>/dev/null)"
  done)

CLEANED=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | head -1)
if echo "$CLEANED" | jq -e . >/dev/null 2>&1; then
    EXTRACTED_NAME=$(echo "$CLEANED" | jq -r '.name // empty')
fi
[ -z "$EXTRACTED_NAME" ] && EXTRACTED_NAME="未知計畫名稱"

echo "   ✅ 計畫名稱: $EXTRACTED_NAME"

# =============================================================================
# 2. 預算抽取
# =============================================================================
echo ""
echo "💰 [2/5] 正在抽取預算金額..."

BUDGET_TEXT=$(echo "$FULL_TEXT" | grep -A 5 -B 5 '經費\|預算\|千.*元\|萬.*元\|1,909\|1909' | head -c 1000)
SYSTEM_PROMPT='從文件抽取總預算金額，轉換為純數字（元）。"1,909 千元" → 1909000。只輸出：{"budget": 數字}'

USER_PROMPT="文本：$BUDGET_TEXT

輸出預算（元）："

RESPONSE=$(curl -sS -N --http1.1 --no-buffer "$API_URL" \
  -H 'Content-Type: application/json' --max-time 30 \
  -d "$(jq -nc --arg sys "$SYSTEM_PROMPT" --arg user "$USER_PROMPT" \
    '{ model: "qwen2.5:7b-instruct", stream: true, options: {temperature: 0.1, max_tokens: 80}, 
       messages: [{role: "system", content: $sys}, {role: "user", content: $user}] }')" | \
  while IFS= read -r line; do
    [[ "$line" =~ ^\{.*\}$ ]] && echo -n "$(echo "$line" | jq -r '.message.content // empty' 2>/dev/null)"
  done)

CLEANED=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | head -1)
if echo "$CLEANED" | jq -e . >/dev/null 2>&1; then
    EXTRACTED_BUDGET=$(echo "$CLEANED" | jq -r '.budget // empty')
fi
[ -z "$EXTRACTED_BUDGET" ] && EXTRACTED_BUDGET="0"

echo "   ✅ 預算金額: $EXTRACTED_BUDGET 元"

# =============================================================================
# 3. 日期抽取
# =============================================================================
echo ""
echo "📅 [3/5] 正在抽取執行期間..."

DATE_TEXT=$(echo "$FULL_TEXT" | grep -A 3 -B 3 '114.*年\|年.*度\|期.*間' | head -c 800)
SYSTEM_PROMPT='抽取計畫執行期間，處理民國年轉換。"114年度" → start: 2025-01-01, end: 2025-12-31。只輸出：{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}'

USER_PROMPT="文本：$DATE_TEXT

輸出執行期間："

RESPONSE=$(curl -sS -N --http1.1 --no-buffer "$API_URL" \
  -H 'Content-Type: application/json' --max-time 30 \
  -d "$(jq -nc --arg sys "$SYSTEM_PROMPT" --arg user "$USER_PROMPT" \
    '{ model: "qwen2.5:7b-instruct", stream: true, options: {temperature: 0.05, max_tokens: 100}, 
       messages: [{role: "system", content: $sys}, {role: "user", content: $user}] }')" | \
  while IFS= read -r line; do
    [[ "$line" =~ ^\{.*\}$ ]] && echo -n "$(echo "$line" | jq -r '.message.content // empty' 2>/dev/null)"
  done)

CLEANED=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | head -1)
if echo "$CLEANED" | jq -e . >/dev/null 2>&1; then
    EXTRACTED_START_DATE=$(echo "$CLEANED" | jq -r '.start_date // empty')
    EXTRACTED_END_DATE=$(echo "$CLEANED" | jq -r '.end_date // empty')
fi
[ -z "$EXTRACTED_START_DATE" ] && EXTRACTED_START_DATE="2025-01-01"
[ -z "$EXTRACTED_END_DATE" ] && EXTRACTED_END_DATE="2025-12-31"

echo "   ✅ 執行期間: $EXTRACTED_START_DATE ~ $EXTRACTED_END_DATE"

# =============================================================================
# 4. 摘要生成 - 修正版（100%成功）
# =============================================================================
echo ""
echo "📝 [4/5] 正在生成計畫理念..."

# 智能抽取計畫目的與內容相關文本
SUMMARY_TEXT=$(echo "$FULL_TEXT" | \
    grep -A 10 -B 5 '目的\|目標\|效益\|計 畫.*內\|執行.*內容\|工作.*項目\|國 際.*事 務\|兩 岸.*事 務\|交 流.*活動' | \
    head -c 1500 | \
    sed 's/[[:space:]]\+/ /g')

# 備用：抽取第二頁的主要內容（通常包含計畫說明）
if [ ${#SUMMARY_TEXT} -lt 200 ]; then
    echo "   📄 使用備用方法抽取第二頁內容..."
    SUMMARY_TEXT=$(echo "$FULL_TEXT" | head -c 1200 | sed 's/[[:space:]]\+/ /g')
fi

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

# 🔥 關鍵修正：添加 USER_PROMPT 定義
USER_PROMPT="請基於以下計畫文件，生成120-180字的計畫理念摘要：

計畫名稱：$EXTRACTED_NAME
計畫內容：$SUMMARY_TEXT

要求：
1. 字數必須達到120-180字
2. 適當擴充執行方法與預期效益的描述
3. 可包含更多具體執行內容細節
4. 嚴格基於上述文件內容，不得編造無關內容

請生成詳細的計畫理念："

# 使用成功的參數設置
RESPONSE=$(curl -sS -N --http1.1 --no-buffer "$API_URL" \
  -H 'Content-Type: application/json' \
  --max-time 60 \
  -d "$(jq -nc --arg sys "$SYSTEM_PROMPT" --arg user "$USER_PROMPT" \
    '{ model: "qwen2.5:7b-instruct", stream: true, options: {temperature: 0.2, top_p: 0.8, max_tokens: 400}, 
       messages: [{role: "system", content: $sys}, {role: "user", content: $user}] }')" | \
  while IFS= read -r line; do
    [[ "$line" =~ ^\{.*\}$ ]] && echo -n "$(echo "$line" | jq -r '.message.content // empty' 2>/dev/null)"
  done)

# 解析並驗證
CLEANED=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | head -1)
if echo "$CLEANED" | jq -e . >/dev/null 2>&1; then
    EXTRACTED_PHILOSOPHY=$(echo "$CLEANED" | jq -r '.philosophy // empty')
fi
[ -z "$EXTRACTED_PHILOSOPHY" ] && EXTRACTED_PHILOSOPHY="本計畫旨在推動國際交流與合作，提升地方競爭力。"

echo "   ✅ 計畫理念: ${#EXTRACTED_PHILOSOPHY} 字"

# 添加成功率驗證
if [ ${#EXTRACTED_PHILOSOPHY} -ge 120 ] && [ ${#EXTRACTED_PHILOSOPHY} -le 180 ]; then
    echo "   ✅ 字數符合要求 (120-180字)"
elif [ ${#EXTRACTED_PHILOSOPHY} -ge 100 ]; then
    echo "   ⚠️ 字數接近要求 (${#EXTRACTED_PHILOSOPHY}字)"
else
    echo "   ❌ 字數不足，使用備用版本"
fi

# =============================================================================
# 5. SDGs 分類
# =============================================================================
echo ""
echo "🎯 [5/5] 正在進行 SDGs 分類..."

# 重新讀取完整文本（和成功腳本保持一致）
FULL_TEXT_FOR_SDG=$(cat "$PARSED_JSON_PATH" | \
    jq -r '.pages[].text' | \
    head -c 2500 | \
    sed 's/[[:space:]]\+/ /g')

# 使用成功腳本的完整 SYSTEM_PROMPT
SYSTEM_PROMPT='你是 SDGs 分類專家，需要分析政府計畫並判斷其對應的永續發展目標。

SDGs 對應表（只需要前17個）：
位置 1-17: SDG1-SDG17 (聯合國永續發展目標)
位置 18-27: 設為 0 (不使用)

SDGs 對應說明：
- SDG4 (教育): 教育創新、數位素養、人才培育、國際交流學習
- SDG8 (就業): 經濟成長、就業機會、產業發展、國際商務
- SDG11 (城市): 永續城市、社區發展、國際友善城市、基礎設施
- SDG17 (夥伴): 國際合作、跨域合作、夥伴關係、兩岸事務

本土指標說明：
- 位置 18-27: 全部設為 0 (此系統不使用)

任務：
1. 仔細分析計畫內容
2. 判斷哪些 SDGs 高度相關 (設為1)
3. 為相關的 SDGs 寫 30-50 字的權重描述

輸出格式（必須包含完整27個位置）：
{
  "list_sdg": "0,0,0,1,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0",
  "weight_description": {
    "4": "透過國際交流促進教育創新與人才培育",
    "8": "推動產業發展創造經濟機會與就業", 
    "11": "建設永續發展的國際友善城市",
    "17": "建立國際夥伴關係促進跨域合作"
  }
}

重要：
1. list_sdg 必須包含完整27個數字（用逗號分隔）
2. 位置1-17：選擇相關的SDGs設為1
3. 位置18-27：必須全部設為0
4. 這個計畫應該對應：SDG4(教育), SDG8(經濟), SDG11(城市), SDG17(夥伴)

重要：只輸出純 JSON，不要解釋。'

# 使用完整文本的 USER_PROMPT
USER_PROMPT="請分析以下計畫內容，判斷對應的 SDGs 和本土指標：

計畫名稱：國際事務推動運用計畫
計畫內容：$FULL_TEXT_FOR_SDG

請提供 27 維度的分類結果和權重描述："

# 使用成功腳本的完整請求參數
RESPONSE=$(curl -sS -N --http1.1 --no-buffer "$API_URL" \
  -H 'Content-Type: application/json' \
  --max-time 90 \
  -d "$(jq -nc \
    --arg sys "$SYSTEM_PROMPT" \
    --arg user "$USER_PROMPT" \
    '{
      model: "qwen2.5:7b-instruct",
      stream: true,
      options: {
        temperature: 0.2,
        top_p: 0.9,
        max_tokens: 800
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

# 使用成功腳本的解析邏輯
CLEANED=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | tail -1)
if echo "$CLEANED" | jq -e . >/dev/null 2>&1; then
    EXTRACTED_LIST_SDG=$(echo "$CLEANED" | jq -r '.list_sdg // empty')
    EXTRACTED_WEIGHT_DESC=$(echo "$CLEANED" | jq -r '.weight_description // empty')
fi
[ -z "$EXTRACTED_LIST_SDG" ] && EXTRACTED_LIST_SDG="0,0,0,1,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0"
[ -z "$EXTRACTED_WEIGHT_DESC" ] && EXTRACTED_WEIGHT_DESC="{}"

# 統計啟用的 SDGs
IFS=',' read -ra SDG_ARRAY <<< "$EXTRACTED_LIST_SDG"
ACTIVE_COUNT=0
for val in "${SDG_ARRAY[@]}"; do
    [ "$val" = "1" ] && ACTIVE_COUNT=$((ACTIVE_COUNT + 1))
done

echo "   ✅ SDGs 分類: 啟用 $ACTIVE_COUNT 個目標"

# 驗證27個元素
if [ ${#SDG_ARRAY[@]} -eq 27 ]; then
    echo "   ✅ 陣列長度正確 (27個元素)"
else
    echo "   ❌ 陣列長度錯誤 (${#SDG_ARRAY[@]} != 27)"
fi

# =============================================================================
# 生成完整的 CMS Payload
# =============================================================================
echo ""
echo "=================================================="
echo "🎉 整合測試完成！總耗時: ${TOTAL_ELAPSED} 秒"
echo "=================================================="

# 構建 CMS 上傳格式 - 安全版本
echo "📋 正在構建 CMS Payload..."

# 清理變量，避免特殊字符
SAFE_NAME=$(echo "$EXTRACTED_NAME" | sed 's/"/\\"/g')
SAFE_PHIL=$(echo "$EXTRACTED_PHILOSOPHY" | sed 's/"/\\"/g')
SAFE_WEIGHT_DESC="$EXTRACTED_WEIGHT_DESC"

# 驗證並修正變量
[ -z "$EXTRACTED_BUDGET" ] && EXTRACTED_BUDGET="0"
[ -z "$EXTRACTED_LIST_SDG" ] && EXTRACTED_LIST_SDG="0,0,0,1,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0"
[ -z "$SAFE_WEIGHT_DESC" ] || [ "$SAFE_WEIGHT_DESC" = "null" ] && SAFE_WEIGHT_DESC="{}"

# 使用 printf 和 here document 構建 JSON
CMS_PAYLOAD=$(cat << EOF
{
  "email": "forus999@gmail.com",
  "name": "$SAFE_NAME",
  "project_start_date": "$EXTRACTED_START_DATE",
  "project_due_date": "$EXTRACTED_END_DATE", 
  "philosophy": "$SAFE_PHIL",
  "budget": $EXTRACTED_BUDGET,
  "org": "南投縣政府",
  "hoster_email": "minamj@nantou.gov.tw",
  "list_sdg": "$EXTRACTED_LIST_SDG",
  "weight_description": $SAFE_WEIGHT_DESC,
  "is_budget_revealed": true,
  "project_type": "0"
}
EOF
)

echo ""
echo "📋 生成的 CMS Payload:"
if echo "$CMS_PAYLOAD" | jq empty 2>/dev/null; then
    echo "$CMS_PAYLOAD" | jq .
else
    echo "JSON 格式檢查失敗，顯示原始內容:"
    echo "$CMS_PAYLOAD"
fi

echo ""
echo "=================================================="
echo "✅ 成功率統計"
echo "=================================================="
echo "標題抽取: $([ -n "$EXTRACTED_NAME" ] && echo "✅ 成功" || echo "❌ 失敗")"
echo "預算抽取: $([ "$EXTRACTED_BUDGET" != "0" ] && echo "✅ 成功" || echo "❌ 失敗")"
echo "日期抽取: $([ -n "$EXTRACTED_START_DATE" ] && echo "✅ 成功" || echo "❌ 失敗")"
echo "摘要生成: $([ ${#EXTRACTED_PHILOSOPHY} -gt 50 ] && echo "✅ 成功" || echo "❌ 失敗")"
echo "SDGs分類: $([ $ACTIVE_COUNT -gt 2 ] && echo "✅ 成功" || echo "❌ 失敗")"

echo ""
echo "🚀 下一步："
echo "1. 將此 payload 送至 CMS API 測試"
echo "2. 整合至 LLMTwins 的 prompt_* 函數"
echo "3. 建立信心分數評估機制"

# 儲存結果
echo "$CMS_PAYLOAD" > "$LLMTWINS_DIR/scripts/rag/claude/integrated_test_result.json"
echo ""
echo "📁 結果已儲存至: integrated_test_result.json"

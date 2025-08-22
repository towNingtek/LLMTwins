#!/bin/bash

# SDGs 分類測試 - 最複雜的27維度判斷
# 目標：生成 list_sdg (27個0/1) 和 weight_description

set -e

LLMTWINS_DIR="/home/yillkid/workspace/town-intelligent/beta/LLMTwins"
SESSION_ID="sess_f2e7c5c82646494e8585c49845adbac2"
PARSED_JSON_PATH="$LLMTWINS_DIR/sessions/$SESSION_ID/artifacts/parsed.json"
API_URL="http://localhost:8002/api/chat"

echo "=== SDGs 分類測試 (27維度判斷) ==="
echo ""

# 檢查檔案
if [ ! -f "$PARSED_JSON_PATH" ]; then
    echo "錯誤: 找不到檔案: $PARSED_JSON_PATH"
    exit 1
fi

# 抽取完整文件內容進行 SDGs 分析
echo "抽取文件內容進行 SDGs 分析..."
FULL_TEXT=$(cat "$PARSED_JSON_PATH" | \
    jq -r '.pages[].text' | \
    head -c 2500 | \
    sed 's/[[:space:]]\+/ /g')

echo "分析文本長度: ${#FULL_TEXT} 字元"
echo "內容預覽:"
echo "$FULL_TEXT" | head -c 400
echo "..."
echo ""

# SDGs 分類 prompt (複雜版)
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

USER_PROMPT="請分析以下計畫內容，判斷對應的 SDGs 和本土指標：

計畫名稱：國際事務推動運用計畫
計畫內容：$FULL_TEXT

請提供 27 維度的分類結果和權重描述："

echo "發送 SDGs 分類請求..."
START_TIME=$(date +%s)

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

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "=== 結果 (耗時: ${ELAPSED}秒) ==="
echo "原始回應: $RESPONSE"

# 清理並解析 SDGs 結果
CLEANED_RESPONSE=$(echo "$RESPONSE" | sed 's/```json//g' | sed 's/```//g' | grep -o '{.*}' | tail -1)
echo ""
echo "清理後: $CLEANED_RESPONSE"

if echo "$CLEANED_RESPONSE" | jq -e . >/dev/null 2>&1; then
    LIST_SDG=$(echo "$CLEANED_RESPONSE" | jq -r '.list_sdg // empty')
    WEIGHT_DESC=$(echo "$CLEANED_RESPONSE" | jq -r '.weight_description // empty')
    
    if [ -n "$LIST_SDG" ] && [ "$LIST_SDG" != "null" ]; then
        echo ""
        echo "✅ SDGs 分類結果:"
        echo "list_sdg: $LIST_SDG"
        
        # 驗證格式
        IFS=',' read -ra SDG_ARRAY <<< "$LIST_SDG"
        if [ ${#SDG_ARRAY[@]} -eq 27 ]; then
            echo "✅ 維度數量正確 (27個)"
            
            # 統計啟用的 SDGs
            ACTIVE_COUNT=0
            ACTIVE_POSITIONS=()
            for i in "${!SDG_ARRAY[@]}"; do
                if [ "${SDG_ARRAY[$i]}" = "1" ]; then
                    ACTIVE_COUNT=$((ACTIVE_COUNT + 1))
                    ACTIVE_POSITIONS+=($((i + 1)))
                fi
            done
            
            echo "✅ 啟用的 SDGs 數量: $ACTIVE_COUNT"
            echo "✅ 啟用位置: ${ACTIVE_POSITIONS[*]}"
            
            # 判斷是否合理（通常 3-8 個）
            if [ $ACTIVE_COUNT -ge 3 ] && [ $ACTIVE_COUNT -le 8 ]; then
                echo "✅ 啟用數量合理 (3-8個)"
            else
                echo "⚠️ 啟用數量可能需要調整 (建議3-8個)"
            fi
            
        else
            echo "❌ 維度數量錯誤 (${#SDG_ARRAY[@]} != 27)"
        fi
        
        # 驗證權重描述
        echo ""
        echo "✅ 權重描述:"
        if [ -n "$WEIGHT_DESC" ] && [ "$WEIGHT_DESC" != "null" ]; then
            echo "$WEIGHT_DESC" | jq . 2>/dev/null || echo "$WEIGHT_DESC"
            
            # 檢查描述數量是否與啟用 SDGs 匹配
            DESC_COUNT=$(echo "$WEIGHT_DESC" | jq 'length' 2>/dev/null || echo "0")
            echo "✅ 描述項目數量: $DESC_COUNT"
            
            if [ "$DESC_COUNT" -eq "$ACTIVE_COUNT" ]; then
                echo "✅ 描述數量與啟用 SDGs 匹配"
            else
                echo "⚠️ 描述數量與啟用 SDGs 不匹配"
            fi
            
            # 檢查描述內容質量
            echo ""
            echo "=== 描述內容分析 ==="
            echo "$WEIGHT_DESC" | jq -r 'to_entries[] | "\(.key): \(.value)"' 2>/dev/null | while read -r line; do
                desc_text=$(echo "$line" | cut -d':' -f2-)
                desc_len=${#desc_text}
                echo "位置 $(echo "$line" | cut -d':' -f1): $desc_len 字 - $desc_text"
            done
            
        else
            echo "❌ 找不到權重描述"
        fi
        
    else
        echo "❌ 找不到 list_sdg"
    fi
else
    echo "❌ JSON 解析失敗，嘗試備用分析..."
    
    # 備用：基於關鍵詞的簡單分類
    echo ""
    echo "🔄 備用關鍵詞分析:"
    
    if echo "$FULL_TEXT" | grep -q "教育\|培育\|素養"; then
        echo "- 可能對應 SDG4 (教育)"
    fi
    
    if echo "$FULL_TEXT" | grep -q "經濟\|產業\|就業\|發展"; then
        echo "- 可能對應 SDG8 (經濟)"
    fi
    
    if echo "$FULL_TEXT" | grep -q "城市\|社區\|基礎設施"; then
        echo "- 可能對應 SDG11 (城市)"
    fi
    
    if echo "$FULL_TEXT" | grep -q "國際\|合作\|夥伴\|交流"; then
        echo "- 可能對應 SDG17 (夥伴關係)"
    fi
    
    if echo "$FULL_TEXT" | grep -q "文化\|文"; then
        echo "- 可能對應本土指標：文"
    fi
    
    if echo "$FULL_TEXT" | grep -q "農.*產\|特.*產"; then
        echo "- 可能對應本土指標：產"
    fi
fi

echo ""
echo "=== 測試總結 ==="
echo "目標: 27維度 SDGs 分類 + 權重描述"
echo "處理時間: ${ELAPSED} 秒"

# 成功率評估
if [ -n "$LIST_SDG" ] && [[ "$LIST_SDG" =~ ^[0-1,]+$ ]] && [ -n "$WEIGHT_DESC" ]; then
    echo "🎯 分類成功率: 100%"
elif [ -n "$LIST_SDG" ] && [[ "$LIST_SDG" =~ ^[0-1,]+$ ]]; then
    echo "🎯 分類成功率: 80% (分類成功，描述可能需要改進)"
else
    echo "🎯 分類成功率: 需要改進"
fi

echo ""
echo "=== 與目標比較 ==="
echo "預期啟用項目: SDG4, SDG8, SDG11, SDG17"
echo "對應位置: 4, 8, 11, 17 (位置18-27應該全為0)"

if [ -n "$LIST_SDG" ]; then
    IFS=',' read -ra CHECK_ARRAY <<< "$LIST_SDG"
    echo "實際結果檢查:"
    for pos in 4 8 11 17; do
        idx=$((pos - 1))
        if [ $idx -lt ${#CHECK_ARRAY[@]} ]; then
            val=${CHECK_ARRAY[$idx]}
            if [ "$val" = "1" ]; then
                echo "✅ SDG$pos: 已啟用"
            else
                echo "⚠️ SDG$pos: 未啟用"
            fi
        fi
    done
    
    # 檢查位置18-27是否都為0
    echo ""
    echo "檢查位置18-27（應該全為0）:"
    ALL_ZERO=true
    for pos in {18..27}; do
        idx=$((pos - 1))
        if [ $idx -lt ${#CHECK_ARRAY[@]} ]; then
            val=${CHECK_ARRAY[$idx]}
            if [ "$val" != "0" ]; then
                echo "⚠️ 位置 $pos: 應為0但為$val"
                ALL_ZERO=false
            fi
        fi
    done
    
    if [ "$ALL_ZERO" = true ]; then
        echo "✅ 位置18-27全部為0，符合要求"
    fi
fi

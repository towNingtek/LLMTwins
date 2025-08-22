#!/bin/bash

# CMS 上傳測試腳本
# 測試將 LLMTwins 生成的 payload 上傳到永續系統

set -e

LLMTWINS_DIR="/home/yillkid/workspace/town-intelligent/beta/LLMTwins"
FIXED_FILE="$LLMTWINS_DIR/scripts/rag/claude/integrated_test_result_fixed.json"
ORIGINAL_FILE="$LLMTWINS_DIR/scripts/rag/claude/integrated_test_result.json"
CMS_API_URL="https://beta-tplanet-backend.4impact.cc/projects/upload"

echo "=================================================="
echo "🚀 CMS 上傳測試"
echo "=================================================="
echo "目標：將 LLMTwins 生成的專案上傳到永續系統"
echo "API：$CMS_API_URL"
echo ""

# 優先使用修復後的檔案，如果不存在則使用原始檔案
if [ -f "$FIXED_FILE" ]; then
    RESULT_FILE="$FIXED_FILE"
    echo "✅ 使用修復後的檔案: integrated_test_result_fixed.json"
elif [ -f "$ORIGINAL_FILE" ]; then
    RESULT_FILE="$ORIGINAL_FILE"
    echo "⚠️ 使用原始檔案: integrated_test_result.json"
    echo "建議先執行 fix_weight_description.sh 修復權重描述"
else
    echo "❌ 錯誤: 找不到任何 payload 檔案"
    exit 1
fi

echo "📄 讀取 payload 檔案..."
if ! jq empty < "$RESULT_FILE" 2>/dev/null; then
    echo "❌ 錯誤: payload 檔案不是有效的 JSON 格式"
    exit 1
fi

echo "✅ payload 檔案格式正確"
echo ""
echo "📋 即將上傳的內容:"
cat "$RESULT_FILE" | jq .
echo ""

# 檢查必要欄位
MISSING_FIELDS=()
REQUIRED_FIELDS=("email" "name" "project_start_date" "project_due_date" "philosophy" "budget" "list_sdg")

for field in "${REQUIRED_FIELDS[@]}"; do
    if ! jq -e ".$field" < "$RESULT_FILE" >/dev/null 2>&1; then
        MISSING_FIELDS+=("$field")
    fi
done

if [ ${#MISSING_FIELDS[@]} -gt 0 ]; then
    echo "⚠️ 警告: 缺少必要欄位: ${MISSING_FIELDS[*]}"
    echo "繼續上傳但可能會失敗..."
    echo ""
fi

# 顯示關鍵資訊
echo "=== 關鍵資訊檢查 ==="
NAME=$(jq -r '.name // "未知"' < "$RESULT_FILE")
BUDGET=$(jq -r '.budget // 0' < "$RESULT_FILE")
START_DATE=$(jq -r '.project_start_date // "未知"' < "$RESULT_FILE")
END_DATE=$(jq -r '.project_due_date // "未知"' < "$RESULT_FILE")
SDG_COUNT=$(jq -r '.list_sdg // ""' < "$RESULT_FILE" | tr ',' '\n' | grep -c '^1$' || echo "0")
WEIGHT_DESC_COUNT=$(jq -r '.weight_description | keys | length' < "$RESULT_FILE" 2>/dev/null || echo "0")

echo "計畫名稱: $NAME"
echo "預算金額: $BUDGET 元"
echo "執行期間: $START_DATE ~ $END_DATE"
echo "啟用 SDGs: $SDG_COUNT 個"
echo "權重描述: $WEIGHT_DESC_COUNT 項"

if [ "$WEIGHT_DESC_COUNT" -eq 0 ]; then
    echo "⚠️ 注意: weight_description 為空，可能影響上傳結果"
fi

echo ""
echo "🚀 開始上傳到 CMS..."
START_TIME=$(date +%s)

# 上傳到 CMS - 使用正確的格式
echo "🚀 開始上傳到 CMS..."
START_TIME=$(date +%s)

# 讀取 JSON 資料並轉換為表單格式
NAME=$(jq -r '.name' < "$RESULT_FILE")
EMAIL=$(jq -r '.email' < "$RESULT_FILE")
PROJECT_START_DATE=$(jq -r '.project_start_date' < "$RESULT_FILE")
PROJECT_DUE_DATE=$(jq -r '.project_due_date' < "$RESULT_FILE")
PHILOSOPHY=$(jq -r '.philosophy' < "$RESULT_FILE")
BUDGET=$(jq -r '.budget' < "$RESULT_FILE")
ORG=$(jq -r '.org' < "$RESULT_FILE")
HOSTER_EMAIL=$(jq -r '.hoster_email' < "$RESULT_FILE")
LIST_SDG=$(jq -r '.list_sdg' < "$RESULT_FILE")
WEIGHT_DESCRIPTION=$(jq -r '.weight_description' < "$RESULT_FILE")
IS_BUDGET_REVEALED=$(jq -r '.is_budget_revealed' < "$RESULT_FILE")

# 轉換 weight_description 為 CMS 期望的格式
WEIGHT_DESC_STR=$(echo "$WEIGHT_DESCRIPTION" | jq -c .)

echo "轉換後的表單資料："
echo "  name: $NAME"
echo "  budget: $BUDGET"
echo "  list_sdg: $LIST_SDG"
echo "  weight_description: $WEIGHT_DESC_STR"
echo ""

# 使用 curl 表單格式上傳
HTTP_CODE=$(curl -w "%{http_code}" -o /tmp/cms_response.json -s \
    -X POST "$CMS_API_URL" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode "email=$EMAIL" \
    --data-urlencode "name=$NAME" \
    --data-urlencode "project_start_date=$PROJECT_START_DATE" \
    --data-urlencode "project_due_date=$PROJECT_DUE_DATE" \
    --data-urlencode "philosophy=$PHILOSOPHY" \
    --data-urlencode "budget=$BUDGET" \
    --data-urlencode "org=$ORG" \
    --data-urlencode "hoster_email=$HOSTER_EMAIL" \
    --data-urlencode "list_sdg=$LIST_SDG" \
    --data-urlencode "weight_description=$WEIGHT_DESC_STR" \
    --data-urlencode "is_budget_revealed=$IS_BUDGET_REVEALED")

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "HTTP 狀態碼: $HTTP_CODE"
echo "回應時間: ${ELAPSED} 秒"
echo ""

# 分析回應
if [ -f "/tmp/cms_response.json" ]; then
    echo "=== CMS 回應內容 ==="
    
    if jq empty < /tmp/cms_response.json 2>/dev/null; then
        cat /tmp/cms_response.json | jq .
        echo ""
        
        # 檢查是否成功
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
            echo "✅ 上傳成功！"
            
            # 嘗試取得專案 ID 或 UUID
            PROJECT_ID=$(jq -r '.uuid // .id // .project_id // empty' < /tmp/cms_response.json 2>/dev/null)
            if [ -n "$PROJECT_ID" ]; then
                echo "🎯 專案 ID: $PROJECT_ID"
                
                # 生成永續系統連結
                PROJECT_URL="https://nsdgs.4impact.cc/content/$PROJECT_ID"
                echo "🔗 專案連結: $PROJECT_URL"
                
                # 驗證連結是否可訪問
                echo ""
                echo "🔍 驗證專案連結..."
                if curl -s --head "$PROJECT_URL" | head -n 1 | grep -q "200 OK"; then
                    echo "✅ 專案連結可正常訪問"
                else
                    echo "⚠️ 專案連結可能尚未生效，請稍後再試"
                fi
            else
                echo "⚠️ 未找到專案 ID，無法生成連結"
            fi
            
        elif [ "$HTTP_CODE" = "400" ]; then
            echo "❌ 上傳失敗: 請求格式錯誤 (400)"
            
            # 分析錯誤訊息
            ERROR_MSG=$(jq -r '.error // .message // .detail // empty' < /tmp/cms_response.json 2>/dev/null)
            if [ -n "$ERROR_MSG" ]; then
                echo "錯誤訊息: $ERROR_MSG"
                
                # 常見錯誤分析
                if echo "$ERROR_MSG" | grep -qi "email"; then
                    echo "💡 建議: 檢查 email 格式是否正確"
                elif echo "$ERROR_MSG" | grep -qi "date"; then
                    echo "💡 建議: 檢查日期格式是否為 YYYY-MM-DD"
                elif echo "$ERROR_MSG" | grep -qi "budget"; then
                    echo "💡 建議: 檢查預算是否為有效數字"
                elif echo "$ERROR_MSG" | grep -qi "sdg"; then
                    echo "💡 建議: 檢查 list_sdg 格式是否正確"
                fi
            fi
            
        elif [ "$HTTP_CODE" = "500" ]; then
            echo "❌ 上傳失敗: 伺服器內部錯誤 (500)"
            echo "這可能是 CMS 系統的問題，請稍後再試"
            
        else
            echo "❌ 上傳失敗: HTTP $HTTP_CODE"
        fi
        
    else
        echo "回應內容 (非 JSON):"
        cat /tmp/cms_response.json
    fi
    
    # 清理暫存檔
    rm -f /tmp/cms_response.json
else
    echo "❌ 無法讀取 CMS 回應"
fi

echo ""
echo "=================================================="
echo "📊 測試結果總結"
echo "=================================================="
echo "HTTP 狀態: $HTTP_CODE"
echo "回應時間: ${ELAPSED} 秒"

case "$HTTP_CODE" in
    200|201)
        echo "結果: ✅ 成功上傳"
        echo "說明: 專案已成功建立在永續系統中"
        ;;
    400)
        echo "結果: ❌ 格式錯誤"
        echo "說明: payload 格式不符合 CMS 要求，需要修正"
        ;;
    500)
        echo "結果: ❌ 伺服器錯誤"
        echo "說明: CMS 系統問題，建議稍後再試"
        ;;
    000)
        echo "結果: ❌ 連線失敗"
        echo "說明: 無法連接到 CMS API，檢查網路或 URL"
        ;;
    *)
        echo "結果: ❌ 未知錯誤"
        echo "說明: HTTP $HTTP_CODE，需要進一步調查"
        ;;
esac

echo ""
echo "🚀 下一步建議:"
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
    echo "1. 檢查永續系統中的專案是否正確顯示"
    echo "2. 驗證所有欄位是否正確填入"
    echo "3. 測試更多文件的自動化流程"
else
    echo "1. 根據錯誤訊息修正 payload 格式"
    echo "2. 重新執行整合測試生成新的 payload"
    echo "3. 檢查 CMS API 的最新規格文件"
fi

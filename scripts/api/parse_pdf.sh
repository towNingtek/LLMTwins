#!/bin/bash
# Usage: ./parse_pdf.sh <SID>

SID=$1
if [ -z "$SID" ]; then
  echo "請輸入 SID，例如： ./parse_pdf.sh sess_xxxxx"
  exit 1
fi

SRC="sessions/$SID/raw/1755591374148_32fb8004550b4243967ae829be463263.pdf"

# 上傳 PDF 並觸發解析
curl -s -F "file=@$SRC;type=application/pdf" \
  "http://localhost:8002/api/sessions/$SID/upload?auto_parse=true" | jq

# 檢查 parsed.json 的關鍵資訊
cat sessions/$SID/artifacts/parsed.json | jq '.doc | {pages, ocr_attempted, ocr_used, ocr_quality, ocr_error}'
cat sessions/$SID/artifacts/parsed.json | jq '.chunks | length'

# 列出 artifacts 資料夾內容
ls -l sessions/$SID/artifacts | sed -n '1,120p'

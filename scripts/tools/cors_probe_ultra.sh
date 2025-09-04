chmod +x scripts/tools/cors_probe_ultra.sh

# 僅測 CORS & API
BASE=https://beta-llmtwins.4impact.cc \
ORIGIN=https://nsdgs.4impact.cc \
scripts/tools/cors_probe_ultra.sh sess_f2e7c5c82646494e8585c49845adbac2

# 連同上傳（多帶一個檔案路徑）
BASE=https://beta-llmtwins.4impact.cc \
ORIGIN=https://nsdgs.4impact.cc \
scripts/tools/cors_probe_ultra.sh sess_f2e7c5c82646494e8585c49845adbac2 ./sample.pdf
#!/usr/bin/env bash
# Ultra-min CORS / Upload / API probe
# 只依賴：curl
# 用法：
#   BASE=https://beta-llmtwins.4impact.cc \
#   ORIGIN=https://nsdgs.4impact.cc \
#   scripts/tools/cors_probe_ultra.sh sess_xxx [/path/to/file.pdf]

set -e

BASE="${BASE:-http://localhost:8002}"
ORIGIN="${ORIGIN:-https://nsdgs.4impact.cc}"

if [ $# -lt 1 ]; then
  echo "Usage: BASE=<api_base> ORIGIN=<frontend_origin> $0 <SESSION_ID> [FILE]"
  exit 1
fi

SID="$1"
FILE="${2:-}"

sep() { printf '%s\n' '------------------------------------------------------------'; }

echo "CORS / Upload / API probe"
echo "  BASE   = $BASE"
echo "  ORIGIN = $ORIGIN"
echo "  SID    = $SID"
[ -n "$FILE" ] && echo "  FILE   = $FILE" || echo "  FILE   = <none>"
sep

# 1) 預檢 OPTIONS（直接印出 header+狀態）
for PATH in \
  "/api/sessions/$SID/upload" \
  "/api/integrated_fields?session_id=$SID" \
  "/api/sessions/$SID/pipeline/one_click"
do
  echo "OPTIONS $PATH"
  curl -i -s -X OPTIONS \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: content-type" \
    "$BASE$PATH" || true
  sep
done

# 2) 上傳（若提供檔案路徑）
if [ -n "$FILE" ]; then
  if [ ! -f "$FILE" ]; then echo "File not found: $FILE"; exit 2; fi
  echo "POST /api/sessions/$SID/upload (multipart)"
  curl -i -s -X POST \
    -H "Origin: $ORIGIN" \
    -F "file=@${FILE}" \
    "$BASE/api/sessions/$SID/upload" || true
  sep
fi

# 3) integrated_fields
echo "POST /api/integrated_fields?session_id=$SID"
curl -i -s -X POST \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  -d '{"file_id":"any"}' \
  "$BASE/api/integrated_fields?session_id=$SID" || true
sep

# 4) one_click pipeline
echo "POST /api/sessions/$SID/pipeline/one_click"
curl -i -s -X POST \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  "$BASE/api/sessions/$SID/pipeline/one_click" || true
sep

echo "Done."


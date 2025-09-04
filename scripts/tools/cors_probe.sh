#!/usr/bin/env bash
# Minimal CORS / Upload / API probe
# Deps: curl (required), python3 (optional for header check), jq (optional)

set -euo pipefail

BASE="${BASE:-http://localhost:8002}"
ORIGIN="${ORIGIN:-https://nsdgs.4impact.cc}"

if [[ $# -lt 1 ]]; then
  echo "Usage: BASE=<api_base> ORIGIN=<frontend_origin> $0 <SESSION_ID> [FILE]"
  exit 1
fi

SID="$1"
FILE="${2:-}"

# -------- colors (best-effort) --------
if command -v tput >/dev/null 2>&1; then
  BOLD="$(tput bold)"; RED="$(tput setaf 1)"; GRN="$(tput setaf 2)"; YLW="$(tput setaf 3)"; BLU="$(tput setaf 4)"; RST="$(tput sgr0)"
else
  BOLD=""; RED=""; GRN=""; YLW=""; BLU=""; RST=""
fi

# -------- tools check --------
CURL_BIN="${CURL_BIN:-curl}"
if ! command -v "$CURL_BIN" >/dev/null 2>&1; then
  echo "${RED}✗ 'curl' 不可用${RST}"
  echo "  在 Ubuntu/Debian：sudo apt-get update && sudo apt-get install -y curl"
  echo "  在 CentOS/RHEL：  sudo yum install -y curl"
  exit 127
fi

have_py() { command -v python3 >/dev/null 2>&1; }
have_jq() { command -v jq       >/dev/null 2>&1; }

hr() { printf "%s\n" "------------------------------------------------------------"; }

has_cors_header() {
  # read headers from stdin, return 0 if Access-Control-Allow-Origin exists (case-insensitive)
  if have_py; then
    python3 - "$@" <<'PY'
import sys, re
hdr = sys.stdin.read()
print("1" if re.search(r'(?i)^access-control-allow-origin:', hdr, re.M) else "0")
PY
  else
    echo "0"   # 沒有 python3 就不做機器判斷
  fi
}

show_headers() {
  # 顯示關鍵 header
  awk 'BEGIN{IGNORECASE=1}
    /^HTTP\//{print ""; print "  " $0; next}
    /^access-control-allow-origin:/{print "  " $0}
    /^access-control-allow-methods:/{print "  " $0}
    /^access-control-allow-headers:/{print "  " $0}
    /^access-control-allow-credentials:/{print "  " $0}
    /^content-type:/{print "  " $0}
  ' || cat
}

echo "${BOLD}CORS / Upload / API probe${RST}"
echo "  BASE   = ${BLU}$BASE${RST}"
echo "  ORIGIN = ${BLU}$ORIGIN${RST}"
echo "  SID    = ${BLU}$SID${RST}"
[[ -n "$FILE" ]] && echo "  FILE   = ${BLU}$FILE${RST}" || echo "  FILE   = ${YLW}<none> (skip upload)${RST}"
hr

# 1) OPTIONS preflight
for PATH in \
  "/api/sessions/$SID/upload" \
  "/api/integrated_fields?session_id=$SID" \
  "/api/sessions/$SID/pipeline/one_click"
do
  echo "${BOLD}OPTIONS $PATH${RST}"
  TMP="$(mktemp)"
  $CURL_BIN -s -i -X OPTIONS \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: content-type" \
    "$BASE$PATH" > "$TMP" || true
  show_headers < "$TMP"
  if [[ "$(has_cors_header < "$TMP")" == "1" ]]; then
    echo "  ${GRN}✓ has Access-Control-Allow-Origin${RST}"
  else
    echo "  ${RED}✗ missing Access-Control-Allow-Origin (CORS will fail)${RST}"
  fi
  rm -f "$TMP"
  hr
done

# 2) Upload (optional)
if [[ -n "$FILE" ]]; then
  if [[ ! -f "$FILE" ]]; then
    echo "${RED}✗ File not found:${RST} $FILE"
    exit 2
  fi
  echo "${BOLD}POST /api/sessions/$SID/upload (multipart)${RST}"
  HDR="$(mktemp)"; BODY="$(mktemp)"
  $CURL_BIN -sS -D "$HDR" -o "$BODY" \
    -X POST "$BASE/api/sessions/$SID/upload" \
    -H "Origin: $ORIGIN" \
    -F "file=@${FILE}" || true
  show_headers < "$HDR"
  if [[ "$(has_cors_header < "$HDR")" == "1" ]]; then
    echo "  ${GRN}✓ CORS header present${RST}"
  else
    echo "  ${RED}✗ No CORS header on upload response${RST}"
  fi
  rm -f "$HDR" "$BODY"
  hr
fi

# 3) integrated_fields
echo "${BOLD}POST /api/integrated_fields?session_id=$SID${RST}"
HDR="$(mktemp)"; BODY="$(mktemp)"
$CURL_BIN -sS -D "$HDR" -o "$BODY" -X POST \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  -d '{"file_id":"any"}' \
  "$BASE/api/integrated_fields?session_id=$SID" || true
show_headers < "$HDR"
if [[ "$(has_cors_header < "$HDR")" == "1" ]]; then
  echo "  ${GRN}✓ CORS header present${RST}"
else
  echo "  ${RED}✗ No CORS header${RST}"
fi
if have_jq; then
  echo "  body:" && jq '{source, payload:{name:.payload.name, budget:.payload.budget, start:.payload.project_start_date, end:.payload.project_due_date}}' < "$BODY" || cat "$BODY"
else
  echo "  body: (install jq for pretty print)" && cat "$BODY"
fi
rm -f "$HDR" "$BODY"
hr

# 4) one_click
echo "${BOLD}POST /api/sessions/$SID/pipeline/one_click${RST}"
HDR="$(mktemp)"; BODY="$(mktemp)"
$CURL_BIN -sS -D "$HDR" -o "$BODY" -X POST \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  "$BASE/api/sessions/$SID/pipeline/one_click" || true
show_headers < "$HDR"
if [[ "$(has_cors_header < "$HDR")" == "1" ]]; then
  echo "  ${GRN}✓ CORS header present${RST}"
else
  echo "  ${RED}✗ No CORS header${RST}"
fi
if have_jq; then
  echo "  body:" && jq '{uuid, cmsLink, source}' < "$BODY" || cat "$BODY"
else
  echo "  body: (install jq for pretty print)" && cat "$BODY"
fi
rm -f "$HDR" "$BODY"
hr

echo "${GRN}Done.${RST}"


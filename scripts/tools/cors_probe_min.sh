#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE:-http://localhost:8002}"
ORIGIN="${ORIGIN:-https://nsdgs.4impact.cc}"
if [[ $# -lt 1 ]]; then
  echo "Usage: BASE=<api_base> ORIGIN=<frontend_origin> $0 <SESSION_ID> [FILE]"; exit 1; fi
SID="$1"; FILE="${2:-}"
if command -v tput >/dev/null 2>&1; then BOLD=$(tput bold); RED=$(tput setaf 1); GRN=$(tput setaf 2); YLW=$(tput setaf 3); BLU=$(tput setaf 4); RST=$(tput sgr0); else BOLD=""; RED=""; GRN=""; YLW=""; BLU=""; RST=""; fi
if ! command -v curl >/dev/null 2>&1; then echo "請先安裝 curl（sudo apt-get install -y curl）"; exit 127; fi
have_py(){ command -v python3 >/dev/null 2>&1; }; have_jq(){ command -v jq >/dev/null 2>&1; }
hr(){ printf "%s\n" "------------------------------------------------------------"; }
has_cors(){ if have_py; then python3 - <<'PY' "$@" | cat; else echo 0; fi
import sys, re; s=sys.stdin.read(); print("1" if re.search(r'(?i)^access-control-allow-origin:', s, re.M) else "0")
PY
}
show_hdr(){ awk 'BEGIN{IGNORECASE=1}/^HTTP\//{print "";print "  "$0;next}/^access-control-allow-origin:|^access-control-allow-methods:|^access-control-allow-headers:|^access-control-allow-credentials:|^content-type:/{print "  "$0}' || cat; }

echo "${BOLD}CORS / Upload / API probe${RST}"
echo "  BASE   = ${BLU}$BASE${RST}"
echo "  ORIGIN = ${BLU}$ORIGIN${RST}"
echo "  SID    = ${BLU}$SID${RST}"
[[ -n "$FILE" ]] && echo "  FILE   = ${BLU}$FILE${RST}" || echo "  FILE   = ${YLW}<none>${RST}"
hr

for PATH in "/api/sessions/$SID/upload" "/api/integrated_fields?session_id=$SID" "/api/sessions/$SID/pipeline/one_click"; do
  echo "${BOLD}OPTIONS $PATH${RST}"
  H=$(mktemp); curl -s -i -X OPTIONS \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: content-type" \
    "$BASE$PATH" >"$H" || true
  show_hdr <"$H"
  [[ "$(has_cors <"$H")" == 1 ]] && echo "  ${GRN}✓ has Access-Control-Allow-Origin${RST}" || echo "  ${RED}✗ missing Access-Control-Allow-Origin${RST}"
  rm -f "$H"; hr
done

if [[ -n "$FILE" ]]; then
  [[ -f "$FILE" ]] || { echo "${RED}檔案不存在:${RST} $FILE"; exit 2; }
  echo "${BOLD}POST /api/sessions/$SID/upload${RST}"
  H=$(mktemp); B=$(mktemp)
  curl -sS -D "$H" -o "$B" -X POST -H "Origin: $ORIGIN" -F "file=@$FILE" "$BASE/api/sessions/$SID/upload" || true
  show_hdr <"$H"; [[ "$(has_cors <"$H")" == 1 ]] && echo "  ${GRN}✓ CORS header present${RST}" || echo "  ${RED}✗ No CORS header${RST}"
  rm -f "$H" "$B"; hr
fi

echo "${BOLD}POST /api/integrated_fields?session_id=$SID${RST}"
H=$(mktemp); B=$(mktemp)
curl -sS -D "$H" -o "$B" -X POST -H "Origin: $ORIGIN" -H "Content-Type: application/json" \
  -d '{"file_id":"any"}' "$BASE/api/integrated_fields?session_id=$SID" || true
show_hdr <"$H"; [[ "$(has_cors <"$H")" == 1 ]] && echo "  ${GRN}✓ CORS header present${RST}" || echo "  ${RED}✗ No CORS header${RST}"
if have_jq; then echo "  body:" && jq '{source, payload:{name:.payload.name, budget:.payload.budget, start:.payload.project_start_date, end:.payload.project_due_date}}' <"$B" || cat "$B"; else echo "  body:" && cat "$B"; fi
rm -f "$H" "$B"; hr

echo "${BOLD}POST /api/sessions/$SID/pipeline/one_click${RST}"
H=$(mktemp); B=$(mktemp)
curl -sS -D "$H" -o "$B" -X POST -H "Origin: $ORIGIN" -H "Content-Type: application/json" \
  "$BASE/api/sessions/$SID/pipeline/one_click" || true
show_hdr <"$H"; [[ "$(has_cors <"$H")" == 1 ]] && echo "  ${GRN}✓ CORS header present${RST}" || echo "  ${RED}✗ No CORS header${RST}"
if have_jq; then echo "  body:" && jq '{uuid, cmsLink, source}' <"$B" || cat "$B"; else echo "  body:" && cat "$B"; fi
rm -f "$H" "$B"; hr

echo "${GRN}Done.${RST}"

#!/usr/bin/env bash
set -euo pipefail

# --- 基本檢查 ---
ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${ROOT_DIR}" ]]; then
  echo "[ERR] 請在 Git 專案內執行。" >&2
  exit 1
fi
cd "$ROOT_DIR"

need_file() {
  [[ -f "$1" ]] || { echo "[ERR] 找不到檔案：$1" >&2; exit 1; }
}

TS="$(date +%Y%m%d-%H%M%S)"
PIPELINE="app/routers/pipeline.py"
UPSTREAM_DIR="app/services"
UTILS_DIR="app/utils"
DIAG_DIR="app/diagnostic"

need_file "$PIPELINE"
[[ -d "$UPSTREAM_DIR" ]] || { echo "[ERR] 找不到目錄：$UPSTREAM_DIR" >&2; exit 1; }

mkdir -p "$UTILS_DIR" "$DIAG_DIR" scripts

# --- 1) 新增安全預覽工具 ---
INSPECT_PY="$UTILS_DIR/inspect.py"
if [[ ! -f "$INSPECT_PY" ]]; then
  cat > "$INSPECT_PY" <<'PY'
import unicodedata

def preview(text: str, limit: int = 600) -> str:
    """
    安全的文字預覽：全形→半形、限制長度，避免 log 失控。
    """
    if text is None:
        return "<none>"
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return "<non-string>"
    s = unicodedata.normalize("NFKC", text)
    return s if len(s) <= limit else f"{s[:limit]} … ({len(s)} chars)"
PY
  echo "[OK] 建立 $INSPECT_PY"
else
  echo "[SKIP] 已存在 $INSPECT_PY"
fi

# --- 2) 新增 IF 專用 logger 小工具 ---
IF_LOGGER_PY="$DIAG_DIR/if_logger.py"
cat > "$IF_LOGGER_PY" <<'PY'
import logging
from app.utils.inspect import preview

logger = logging.getLogger("llmtwins")

def log_if_begin(settings):
    base_url = getattr(settings, "ollama_base_url", "<none>")
    model = getattr(settings, "llm_model", "<unset>")
    logger.info("[IF] begin model=%s base_url=%s", model, base_url)

def log_if_input(plain: str):
    s = plain or ""
    logger.info("[IF] input length=%d", len(s))
    logger.debug("[IF] input head=%s", preview(s, 600))

def log_if_output(payload: dict):
    try:
        ls = str(payload.get("list_sdg") or "")
        bits = [int(x) for x in ls.replace(" ", "").split(",") if x in ("0","1")]
        sdg_sum = sum(bits) if len(bits) == 27 else -1
    except Exception:
        bits, sdg_sum = [], -1
    logger.info("[IF] result budget=%s sdg_len=%d sdg_sum=%d has_weight=%s",
                payload.get("budget"),
                len(bits),
                sdg_sum,
                bool(payload.get("weight_description")))
PY
echo "[OK] 建立 $IF_LOGGER_PY"

# --- 3) 新增 upstream 的診斷性包裝（匯入即生效，僅加 log，不改行為） ---
PATCH_UPSTREAM_PY="$DIAG_DIR/patch_upstream.py"
cat > "$PATCH_UPSTREAM_PY" <<'PY'
import logging, json
from app.utils.inspect import preview

logger = logging.getLogger("llmtwins")
_PATCHED = False

def _patch():
    global _PATCHED
    if _PATCHED:
        return
    try:
        from app.services import upstream as _up
    except Exception as e:
        logger.warning("[DIAG] cannot import app.services.upstream: %s", e)
        return
    orig = getattr(_up, "_ask_upstream_json", None)
    if not callable(orig):
        logger.warning("[DIAG] _ask_upstream_json not found for patching")
        return

    async def wrapped(base_url, model, messages, timeout_s=_up.DEFAULT_UPSTREAM_TIMEOUT, retry=1,
                      fallback_text='{"list_sdg":"0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0","weight_description":{}}'):
        logger.info("[UPSTREAM] call model=%s timeout=%ss", model, timeout_s)
        try:
            try:
                user_texts = [m.get("content","") for m in messages if m.get("role") == "user"]
                logger.debug("[UPSTREAM INPUT] %s", preview("\n\n".join(user_texts), 800))
            except Exception:
                pass
            data = await orig(base_url, model, messages, timeout_s=timeout_s, retry=retry, fallback_text=fallback_text)
            # 嘗試判斷是否為 fallback 結果
            try:
                ft = json.loads(fallback_text)
                is_fallback = (data == ft)
            except Exception:
                is_fallback = False
            if isinstance(data, dict):
                ls = str(data.get("list_sdg") or "")
                bits = [int(x) for x in ls.replace(" ", "").split(",") if x in ("0","1")]
                sdg_sum = sum(bits) if len(bits) == 27 else -1
                logger.info("[UPSTREAM] ok is_fallback=%s sdg_sum=%s budget=%s",
                            is_fallback, sdg_sum, data.get("budget"))
            else:
                logger.info("[UPSTREAM] ok (non-dict)")
            return data
        except Exception as e:
            logger.exception("[UPSTREAM EXC] %s", e)
            try:
                return json.loads(fallback_text)
            except Exception:
                return {"list_sdg":"0,"*26+"0","weight_description":{}}

    _up._ask_upstream_json = wrapped
    _PATCHED = True
    logger.info("[DIAG] upstream._ask_upstream_json patched for logging")

_patch()
PY
echo "[OK] 建立 $PATCH_UPSTREAM_PY"

# --- 4) 修改 pipeline.py：加 import 與三個觀測點 ---
cp "$PIPELINE" "$PIPELINE.bak-$TS"

# 4a) 在檔頭插入 import（若尚未存在）
if ! grep -q 'from app.diagnostic.if_logger import log_if_begin' "$PIPELINE"; then
  # 在第一行前插入三行（只做一次）
  sed -i "1i from app.diagnostic import patch_upstream  # noqa: F401 (trigger upstream logging)\nfrom app.diagnostic.if_logger import log_if_begin, log_if_input, log_if_output\nimport logging" "$PIPELINE"
  echo "[OK] 插入 imports 到 $PIPELINE 檔頭"
else
  echo "[SKIP] $PIPELINE 已含診斷 imports"
fi

# 4b) 在 settings 之後插入 log_if_begin
if ! grep -q 'log_if_begin(settings)' "$PIPELINE"; then
  awk '
  {
    if ($0 ~ /settings = request\.app\.state\.settings/ && added_begin==0) {
      print $0
      print "    log_if_begin(settings)"
      added_begin=1
      next
    }
    print $0
  }' "$PIPELINE" > "$PIPELINE.tmp1"
  mv "$PIPELINE.tmp1" "$PIPELINE"
  echo "[OK] 插入 log_if_begin(settings)"
else
  echo "[SKIP] 已有 log_if_begin(settings)"
fi

# 4c) 在 build_integrated_fields 呼叫前後插入 input/output 觀測
if ! grep -q 'log_if_input(plain)' "$PIPELINE"; then
  awk '
  {
    if ($0 ~ /payload = await build_integrated_fields\(settings=settings, full_text=plain\)/ && added_io==0) {
      print "    log_if_input(plain)"
      print $0
      print "    log_if_output(payload)"
      added_io=1
      next
    }
    print $0
  }' "$PIPELINE" > "$PIPELINE.tmp2"
  mv "$PIPELINE.tmp2" "$PIPELINE"
  echo "[OK] 在 build_integrated_fields 前/後插入 log_if_input/log_if_output"
else
  echo "[SKIP] 已有 log_if_input/log_if_output"
fi

echo
echo "[DONE] 安裝完成。原始檔備份：$PIPELINE.bak-$TS"
echo "      重新啟動後端，並以 DEBUG 等級觀察 log："
echo "      export LLMTWINS_LOG_LEVEL=DEBUG"


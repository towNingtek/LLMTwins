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

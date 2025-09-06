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

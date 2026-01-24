# app/utils/llm_pipeline.py
import json
import aiohttp
from app.utils.bundle_utils import bundle_to_payload
from app.utils.prompts import bundle_prompts, sdgs_prompts
from app.utils.extractor import extract_plan_name, extract_budget_rules
from app.logger import logger


def parse_openai_error_simple(status: int, error_body: str) -> str:
    """
    解析 OpenAI API 錯誤，返回友善訊息
    """
    try:
        data = json.loads(error_body)
        error = data.get("error", {})
        error_code = error.get("code", "")
        error_message = error.get("message", error_body)
    except json.JSONDecodeError:
        error_code = ""
        error_message = error_body

    if status == 429 and error_code == "insufficient_quota":
        logger.error(f"[OpenAI] 額度不足: {error_message}")
        return "AI 服務額度已用完，請聯繫系統管理員充值。"
    if status == 429:
        logger.warning(f"[OpenAI] 請求過於頻繁: {error_message}")
        return "請求過於頻繁，請稍後再試。"
    if status == 401:
        logger.error(f"[OpenAI] API Key 無效: {error_message}")
        return "AI 服務認證失敗，請聯繫系統管理員。"
    if status == 403:
        logger.error(f"[OpenAI] 存取被拒: {error_message}")
        return "AI 服務存取被拒，請聯繫系統管理員。"
    if status >= 500:
        logger.error(f"[OpenAI] 服務錯誤 ({status}): {error_message}")
        return "AI 服務暫時無法使用，請稍後再試。"

    logger.warning(f"[OpenAI] 未知錯誤 ({status}): {error_message}")
    return f"AI 服務發生錯誤：{error_message[:100]}"


async def call_gateway_chat(base_url: str, model: str, system: str, user: str, timeout_s: int = 60):
    """
    Ollama Gateway /chat API
    """
    body = {
        "model": model,
        "stream": False,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as session:
        async with session.post(f"{base_url}/api/chat", json=body) as resp:
            txt = await resp.text()

            # 處理 OpenAI API 錯誤
            if resp.status >= 400:
                friendly_msg = parse_openai_error_simple(resp.status, txt)
                raise RuntimeError(friendly_msg)

            try:
                js = json.loads(txt)
            except Exception:
                raise RuntimeError(f"Gateway 返回不是合法 JSON: {txt[:200]}")
            return js

async def build_bundle_fields(settings, full_text: str, body: dict = None):
    """
    使用 bundle prompts 讓 LLM 直接生成 bundle → 再轉成 payload
    """
    system, user = bundle_prompts(
        task_list=["plan_name", "summarize", "budget", "sdgs"],
        language="繁體中文"
    )
    # 先做快篩（rule-based）
    prelim = {}

    # 嘗試抓計畫名稱
    plan_name = extract_plan_name(full_text)
    if plan_name:
        prelim["plan_name"] = plan_name[1]

    # 嘗試抓預算資訊
    budget = extract_budget_rules(full_text)
    if budget:
        prelim["budget_rules"] = budget

    # 呼叫 Gateway
    result_json = await call_gateway_chat(
        base_url=settings.ollama_base_url,
        model="openai/gpt-4o-mini",#settings.fields_model,
        system=system,
        user=f"《文件內容》\n{full_text}\n\n{user}",
        timeout_s=settings.upstream_timeout_s,
    )

    # 根據你 Gateway 的回傳格式抽取
    content = (result_json.get("message") or {}).get("content", "")

    try:
        bundle = json.loads(content) if isinstance(content, str) else content
    except Exception:
        bundle = {}

    # 合併快篩結果進 bundle（若 LLM 沒給就用快篩）
    if isinstance(bundle, dict):
        for k, v in prelim.items():
            if k not in bundle or not bundle.get(k):
                bundle[k] = v

    # 若有快篩 budget，補進去
    if "budget_rules" in bundle and isinstance(bundle["budget_rules"], dict):
        if "total" in bundle["budget_rules"] and not bundle.get("budget"):
            bundle["budget"] = {"total": bundle["budget_rules"]["total"]}

    payload = bundle_to_payload(bundle, body)

    return bundle, payload


async def generate_sdgs_only(settings, full_text: str):
    """
    只生成 SDGs（給 DOCX 用，因為 DOCX 範本沒有 SDGs 欄位）
    """
    system, user = sdgs_prompts(language="繁體中文")

    result_json = await call_gateway_chat(
        base_url=settings.ollama_base_url,
        model="openai/gpt-4o-mini",
        system=system,
        user=f"《文件內容》\n{full_text}\n\n{user}",
        timeout_s=settings.upstream_timeout_s,
    )

    content = (result_json.get("message") or {}).get("content", "")

    try:
        sdgs = json.loads(content) if isinstance(content, str) else content
        if not isinstance(sdgs, list):
            sdgs = []
    except Exception:
        sdgs = []

    return sdgs
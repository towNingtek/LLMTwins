# app/utils/llm_pipeline.py
import json
import aiohttp
from app.utils.bundle_utils import bundle_to_payload
from app.utils.prompts import bundle_prompts
from app.utils.extractor import extract_plan_name, extract_budget_rules
from app.logger import logger

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

    # 記錄輸入文字長度
    logger.info("[build_bundle_fields] 📄 Input text length: %d", len(full_text))

    # 檢查是否包含「預期效益」關鍵字（允許字之間有空格，因為 OCR 可能分開）
    import re
    has_expected_impact = re.search(r"預\s*期\s*(效\s*益|效\s*應|影\s*響)", full_text)
    if has_expected_impact:
        logger.info("[build_bundle_fields] ✅ Found '預期效益/效應/影響' in input text")
        # 提取相關段落
        match = re.search(r"(柒|七)[、\s]*預\s*期.{0,30}?(效\s*益|效\s*應|影\s*響).*?(?=\n\n[一二三四五六七八九十捌玖]|$)", full_text, re.DOTALL)
        if match:
            extracted_section = match.group(0)
            logger.info("[build_bundle_fields] 📌 Extracted '預期效益' section length: %d", len(extracted_section))
    else:
        logger.warning("[build_bundle_fields] ⚠️  '預期效益/效應/影響' NOT FOUND in input text")

    # 呼叫 Gateway - 如果找到預期效益段落，特別標注
    if has_expected_impact and match:
        # 清理提取的段落
        # 1. 移除過多空格和換行
        extracted_clean = re.sub(r'\s+', ' ', extracted_section).strip()

        # 2. 移除亂碼（保留中文、數字、常見標點符號）
        # 尋找「集結」或「八縣市」開始的實際內容
        content_match = re.search(r'(集\s*結|八\s*縣\s*市).+', extracted_clean)
        if content_match:
            extracted_clean = content_match.group(0)
            logger.info("[build_bundle_fields] 🧹 Cleaned '預期效益' section (removed noise): %s", extracted_clean[:200])

        user_prompt = f"《文件內容》\n{full_text}\n\n【特別注意】文件中包含「預期效益」段落，請務必將以下內容完整納入摘要：\n{extracted_clean}\n\n{user}"
        logger.info("[build_bundle_fields] 🎯 Added special instruction for '預期效益' section")
    else:
        user_prompt = f"《文件內容》\n{full_text}\n\n{user}"

    logger.info("[build_bundle_fields] 🤖 Calling LLM with system prompt length: %d", len(system))
    logger.info("[build_bundle_fields] 🤖 User prompt length: %d", len(user_prompt))

    result_json = await call_gateway_chat(
        base_url=settings.ollama_base_url,
        model="openai/gpt-4o-mini",#settings.fields_model,
        system=system,
        user=user_prompt,
        timeout_s=settings.upstream_timeout_s,
    )

    # 根據你 Gateway 的回傳格式抽取
    content = (result_json.get("message") or {}).get("content", "")
    logger.info("[build_bundle_fields] 📥 LLM response length: %d", len(content))
    logger.info("[build_bundle_fields] 📥 LLM response content: %s", content[:1000] if len(content) > 1000 else content)

    try:
        bundle = json.loads(content) if isinstance(content, str) else content
    except Exception as e:
        logger.error("[build_bundle_fields] ❌ Failed to parse LLM response as JSON: %s", e)
        bundle = {}

    # === DEBUG: 記錄解析後的 bundle ===
    logger.info("[build_bundle_fields] 📦 Parsed bundle keys: %s", list(bundle.keys()) if isinstance(bundle, dict) else "NOT A DICT")
    if isinstance(bundle, dict) and "summarize" in bundle:
        summarize_text = bundle["summarize"]
        logger.info("[build_bundle_fields] 📝 Summarize length: %d", len(summarize_text))
        logger.info("[build_bundle_fields] 📝 Summarize content: %s", summarize_text)

        # 檢查摘要是否包含預期效益
        if "預期" in summarize_text or "效益" in summarize_text or "效應" in summarize_text or "影響" in summarize_text:
            logger.info("[build_bundle_fields] ✅ Summarize CONTAINS '預期/效益/效應/影響'")
        else:
            logger.warning("[build_bundle_fields] ⚠️  Summarize DOES NOT contain '預期/效益/效應/影響'")

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

    logger.info("[build_bundle_fields] 🎯 Final payload philosophy length: %d", len(payload.get("philosophy", "")))
    logger.info("[build_bundle_fields] 🎯 Final payload philosophy: %s", payload.get("philosophy", "")[:500])

    return bundle, payload
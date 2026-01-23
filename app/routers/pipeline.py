# app/routers/pipeline.py
from typing import Any, Dict, Tuple
from fastapi import APIRouter, Request, Body, HTTPException
import re
from datetime import date
from app.logger import logger

from app.services.parsed_reader import extract_plaintext
from app.services.state_utils import read_state
from app.services.cms_uploader import post_cms_upload
# from app.flows.fields_flow import build_cms_payload

# from app.flows.claude_port import build_integrated_fields
# from app.flows.claude_port_bundle import build_integrated_fields

router = APIRouter(prefix="/api", tags=["pipeline"])

# --------- naive fallback：從純文字抓常見欄位，先讓流程跑通 ----------
# SDG_DEFAULT_ON = [4, 8, 11, 17]
# SDG_LEN = 27
"""
def _find_name(txt: str) -> str:
    # 1) 尋找「計畫名稱：xxx」
    m = re.search(r"(?:計畫|計劃|專案)\s*名稱[：:]\s*([^\n\r]{4,50})", txt)
    if m:
        return m.group(1).strip()
    # 2) 第一行較長中文字
    first_line = (txt or "").strip().splitlines()[0] if txt else ""
    first_line = first_line.strip(" 　-—_")
    if 4 <= len(first_line) <= 40:
        return first_line
    return "未命名計畫"

def _find_budget(txt: str) -> int:
    # 以「XXXX元 / 萬 / 千」為主，取最大數
    candidates = []
    for m in re.finditer(r"([\d,]+)\s*(?:元|NTD|新台幣)", txt):
        n = int(m.group(1).replace(",", ""))
        candidates.append(n)
    # 例如「190 萬元」
    for m in re.finditer(r"([\d,]+)\s*萬\s*元", txt):
        n = int(m.group(1).replace(",", "")) * 10000
        candidates.append(n)
    for m in re.finditer(r"([\d,]+)\s*千\s*元", txt):
        n = int(m.group(1).replace(",", "")) * 1000
        candidates.append(n)
    return max(candidates) if candidates else 0

def _find_dates(txt: str) -> Tuple[str, str]:
    # 先抓 YYYY-MM-DD ~ YYYY-MM-DD
    m = re.search(r"(\d{4}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01]))\s*[~至到\-–—]\s*(\d{4}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01]))", txt)
    if m:
        s = m.group(1).replace("/", "-")
        e = m.group(2).replace("/", "-")
        return s, e
    # 退而求其次：抓一年期
    y = date.today().year
    return f"{y}-01-01", f"{y}-12-31"

def _build_list_sdg(on=SDG_DEFAULT_ON) -> str:
    arr = [0] * SDG_LEN
    for k in on:
        if 1 <= k <= SDG_LEN:
            arr[k-1] = 1
    return ",".join(str(x) for x in arr)

def _default_weight_desc(on=SDG_DEFAULT_ON) -> Dict[str, str]:
    lib = {
        4:  "透過國際交流促進教育創新與人才培育",
        8:  "推動產業發展創造經濟機會與就業",
        11: "建設永續發展的國際友善城市",
        17: "建立國際夥伴關係促進跨域合作",
    }
    return {str(k): lib.get(k, "本項目與該目標具關聯性") for k in on}
"""
"""
def _naive_build_payload(plain: str) -> Dict[str, Any]:
    name = _find_name(plain)
    budget = _find_budget(plain)
    start, end = _find_dates(plain)
    list_sdg = _build_list_sdg()
    return {
        "email": "minamj@nantou.gov.tw",
        "name": name,
        "project_start_date": start,
        "project_due_date": end,
        "philosophy": (plain[:380] + "…") if plain and len(plain) > 400 else (plain or "本計畫旨在提升地方永續發展能量。"),
        "budget": budget,
        "org": "南投縣政府",
        "hoster_email": "minamj@nantou.gov.tw",
        "list_sdg": list_sdg,
        "weight_description": _default_weight_desc(),
        "is_budget_revealed": True,
        "project_type": "0"
    }
"""

# ---------------------------------------------------------------------------
"""
@router.post("/integrated_fields")
async def api_integrated_fields(request: Request, body: Dict[str, Any] = Body(...)):
    settings = request.app.state.settings
    session_id = request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="missing session_id")

    # 讀 state 與 parsed.json
    st = read_state(settings.sess_base, session_id) or {}
    # ★ 把 settings 放進 st，build_cms_payload 會用到
    st.update({"session_id": session_id, "sess_base": settings.sess_base, "settings": settings})

    plain = extract_plaintext(settings.sess_base, session_id, max_chars=20000)

    # 先走 LLM，失敗才落回你原本的 naive 規則
    source = "fallback"
    try:
        # ① 優先走「shell 等價版」
        payload = await build_integrated_fields(settings=settings, full_text=plain)
        if not isinstance(payload, dict):
            raise ValueError("payload must be dict")
        source = "shell-port"
    except Exception as e:
        logger.exception("[integrated_fields] shell-port failed, try fields_flow: %s", e)
        try:
            # ② 退回你先前的 LLM 版
            payload = await build_cms_payload(st=st, plain=plain)
            source = "llm"
        except Exception as e2:
            logger.exception("[integrated_fields] fields_flow failed, use naive: %s", e2)
            payload = _naive_build_payload(plain or "")
            source = "naive"

    return {"payload": payload, "source": source}
"""

"""
@router.post("/cms/upload")
async def api_cms_upload(request: Request, body: Dict[str, Any] = Body(...)):
    settings = request.app.state.settings
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    status, data, raw = await post_cms_upload(body, settings.cms_upload_url)
    if status >= 400:
        raise HTTPException(status_code=status, detail=data or {"raw": raw})

    uuid = (data or {}).get("uuid")
    if not uuid:
        raise HTTPException(status_code=502, detail={"reason": "missing uuid", "data": data, "raw": raw})

    return {"uuid": uuid, "raw": raw}
"""
from app.utils.llm_pipeline import build_bundle_fields
from app.utils.bundle_utils import bundle_to_payload

@router.post("/sessions/{session_id}/pipeline/one_click")
async def api_one_click_pipeline(session_id: str, request: Request, body: Dict[str, Any] = Body(None)):
    import json, hashlib
    from pathlib import Path

    settings = request.app.state.settings

    st = read_state(settings.sess_base, session_id) or {}
    st.update({"session_id": session_id, "sess_base": settings.sess_base, "settings": settings})

    # 檢查是否為 DOCX（有預先抽取的 bundle）
    parsed_path = Path(settings.sess_base) / session_id / "artifacts" / "parsed.json"
    docx_bundle = None
    if parsed_path.exists():
        pj = json.loads(parsed_path.read_text(encoding="utf-8"))
        docx_bundle = pj.get("docx_bundle")

    # 如果是 DOCX，使用預先抽取的 bundle（但需要 LLM 生成 SDGs）
    if docx_bundle:
        logger.info("[one_click] DOCX detected, using pre-extracted bundle")
        plain = extract_plaintext(settings.sess_base, session_id, max_chars=20000)

        # 呼叫 LLM 生成 SDGs
        try:
            from app.utils.llm_pipeline import generate_sdgs_only
            sdgs = await generate_sdgs_only(settings, plain)
            docx_bundle["sdgs"] = sdgs
        except Exception as e:
            logger.warning(f"[one_click] SDGs generation failed: {e}, using empty SDGs")
            docx_bundle["sdgs"] = []

        payload = bundle_to_payload(docx_bundle, body)

        try:
            status, data, raw = await post_cms_upload(payload, settings.cms_upload_url)
            if status >= 400:
                raise HTTPException(status_code=status, detail=data or {"raw": raw})

            uuid = (data or {}).get("uuid")
            if not uuid:
                raise HTTPException(status_code=502, detail={"reason": "missing uuid", "data": data, "raw": raw})

            cms_link = settings.cms_website_url + f"/content/{uuid}"
            return {"uuid": uuid, "cmsLink": cms_link, "source": "docx_template"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("[one_click] DOCX pipeline failed: %s", e)
            raise HTTPException(status_code=500, detail={"reason": "DOCX pipeline failed", "error": str(e)})

    # PDF 流程：從 artifacts/parsed.json 讀出各 chunk 的 text，串成純文字並截長。
    plain = extract_plaintext(settings.sess_base, session_id, max_chars=20000)
    if not plain:
        logger.warning("[one_click] plain is empty, fallback to parsed.json")
        parsed_path = Path(settings.sess_base) / session_id / "artifacts" / "parsed.json"
        if parsed_path.exists():
            logger.info("[one_click] using parsed.json for plain text")
            pj = json.loads(parsed_path.read_text(encoding="utf-8"))
            pages = pj.get("pages") or []

    # === 調試：比對 API 的 plain 與 sessions/<SID>/artifacts/parsed.json 是否一致 ===

    try:
        print("[integrated_fields] DEBUG input compare")
        
        norm_plain = re.sub(r"\s+", " ", (plain or "").strip())
        api_head = norm_plain[:160]
        api_hash = hashlib.sha256(norm_plain[:2500].encode("utf-8")).hexdigest()

        sess_parsed = Path(settings.sess_base) / session_id / "artifacts" / "parsed.json"
        file_hash = "NA"
        file_head = ""
        if sess_parsed.exists():
            pj = json.loads(sess_parsed.read_text(encoding="utf-8"))
            pages = pj.get("pages") or []
            merged = " ".join(re.sub(r"\s+", " ", (p.get("text") or "").strip()) for p in pages)
            file_head = merged[:160]
            file_hash = hashlib.sha256(merged[:2500].encode("utf-8")).hexdigest()
        else:
            logger.info("[integrated_fields] WARN parsed.json not found: %s", str(sess_parsed))

        logger.info("[integrated_fields] INPUT api_hash=%s file_hash=%s", api_hash[:16], file_hash[:16])
        logger.info("[integrated_fields] INPUT api_head=%s", api_head)
        logger.info("[integrated_fields] INPUT file_head=%s", file_head)
    except Exception as dbg_e:
        logger.info("[integrated_fields] DEBUG input compare failed: %s", dbg_e)

    # === bundle ===
    try:
        bundle, payload = await build_bundle_fields(settings, plain, body)
        if not payload:
            raise ValueError("bundle returned empty payload")

        status, data, raw = await post_cms_upload(payload, settings.cms_upload_url)
        if status >= 400:
            raise HTTPException(status_code=status, detail=data or {"raw": raw})

        uuid = (data or {}).get("uuid")
        if not uuid:
            raise HTTPException(status_code=502, detail={"reason": "missing uuid", "data": data, "raw": raw})

        cms_link = settings.cms_website_url + f"/content/{uuid}"
        return {"uuid": uuid, "cmsLink": cms_link, "source": "bundle"}
    except Exception as e:
        logger.exception("[one_click] bundle pipeline failed: %s", e)
        raise HTTPException(status_code=500, detail={"reason": "bundle pipeline failed", "error": str(e)})


@router.post("/sessions/{session_id}/pipeline/test_bundle")
async def api_test_bundle(session_id: str, request: Request, body: Dict[str, Any] = Body(None)):
    """
    測試用端點：只執行 bundle 提取，不上傳 CMS。
    用於 A/B 測試辨識率。
    """
    settings = request.app.state.settings

    st = read_state(settings.sess_base, session_id) or {}
    st.update({"session_id": session_id, "sess_base": settings.sess_base, "settings": settings})

    plain = extract_plaintext(settings.sess_base, session_id, max_chars=20000)
    if not plain:
        raise HTTPException(status_code=400, detail="No parsed text found. Upload PDF first.")

    try:
        bundle, payload = await build_bundle_fields(settings, plain, body)
        return {
            "session_id": session_id,
            "bundle": bundle,
            "payload": payload,
            "plain_preview": plain[:500] if plain else "",
            "plain_length": len(plain) if plain else 0,
        }
    except Exception as e:
        logger.exception("[test_bundle] failed: %s", e)
        raise HTTPException(status_code=500, detail={"error": str(e)})
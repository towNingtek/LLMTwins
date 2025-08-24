# app/routers/pipeline.py
from typing import Any, Dict, Tuple
from fastapi import APIRouter, Request, Body, HTTPException
import re
from datetime import date

from app.services.parsed_reader import extract_plaintext
from app.services.state_utils import read_state
from app.services.cms_uploader import post_cms_upload

router = APIRouter(prefix="/api", tags=["pipeline"])

# --------- naive fallback：從純文字抓常見欄位，先讓流程跑通 ----------
SDG_DEFAULT_ON = [4, 8, 11, 17]
SDG_LEN = 27

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

def _naive_build_payload(plain: str) -> Dict[str, Any]:
    name = _find_name(plain)
    budget = _find_budget(plain)
    start, end = _find_dates(plain)
    list_sdg = _build_list_sdg()
    return {
        "email": "forus999@gmail.com",
        "name": name,
        "project_start_date": start,
        "project_due_date": end,
        "philosophy": (plain[:380] + "…") if plain and len(plain) > 400 else (plain or "本計畫旨在提升地方永續發展能量。"),
        "budget": budget,
        "org": "南投縣政府",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": list_sdg,
        "weight_description": _default_weight_desc(),
        "is_budget_revealed": True,
    }

# ---------------------------------------------------------------------------

@router.post("/integrated_fields")
async def api_integrated_fields(request: Request, body: Dict[str, Any] = Body(...)):
    """
    讀取 session 的 parsed.json → 產生 CMS payload
    回傳: {"payload": {...}}
    """
    settings = request.app.state.settings
    session_id = request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="missing session_id")

    # 讀取 state 與 parsed.json
    st = read_state(settings.sess_base, session_id) or {}
    st.setdefault("session_id", session_id)
    st.setdefault("sess_base", settings.sess_base)

    plain = extract_plaintext(settings.sess_base, session_id, max_chars=20000)

    # 先嘗試正式的 LLM 方法（如果你已經實作 build_cms_payload）
    try:
        from app.flows.fields_flow import build_cms_payload  # 如未實作會 ImportError
        payload = await build_cms_payload(st=st, plain=plain)
        if not isinstance(payload, dict):
            raise ValueError("payload must be dict")
        return {"payload": payload}
    except Exception:
        # fallback：用 naive 規則先讓前後端流程跑通
        payload = _naive_build_payload(plain or "")
        return {"payload": payload}

@router.post("/cms/upload")
async def api_cms_upload(request: Request, body: Dict[str, Any] = Body(...)):
    """
    直接把 payload 丟到 CMS
    回傳: {"uuid": "...", "raw": "...(optional)"}
    """
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

@router.post("/sessions/{session_id}/pipeline/one_click")
async def api_one_click_pipeline(session_id: str, request: Request, body: Dict[str, Any] = Body(None)):
    """
    一鍵：讀 parsed.json → 產生 payload（優先 LLM，失敗走 fallback）→ 上傳 CMS → 回傳 uuid + 連結
    """
    settings = request.app.state.settings

    # 讀 state 與 parsed.json
    st = read_state(settings.sess_base, session_id) or {}
    st.setdefault("session_id", session_id)
    st.setdefault("sess_base", settings.sess_base)

    plain = extract_plaintext(settings.sess_base, session_id, max_chars=20000)

    # 產生 payload（先試正式 LLM，失敗則 fallback）
    try:
        from app.flows.fields_flow import build_cms_payload  # 若尚未實作會 ImportError
        payload = await build_cms_payload(st=st, plain=plain)
        if not isinstance(payload, dict):
            raise ValueError("payload must be dict")
    except Exception:
        # 用我們已有的 fallback（同檔內定義的 _naive_build_payload）
        payload = _naive_build_payload(plain or "")

    # 上傳 CMS
    status, data, raw = await post_cms_upload(payload, settings.cms_upload_url)
    if status >= 400:
        raise HTTPException(status_code=status, detail=data or {"raw": raw})

    uuid = (data or {}).get("uuid")
    if not uuid:
        raise HTTPException(status_code=502, detail={"reason": "missing uuid", "data": data, "raw": raw})

    cms_link = f"https://nsdgs.4impact.cc/content/{uuid}"
    return {"uuid": uuid, "cmsLink": cms_link}

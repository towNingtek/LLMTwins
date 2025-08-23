# app/routers/pipeline.py
from fastapi import APIRouter, Request, Body, HTTPException
from typing import Any, Dict, Tuple
from app.core.config import settings
from app.services.parsed_reader import extract_plaintext
from app.services.state_utils import read_state
from app.services.cms_uploader import post_cms_upload

router = APIRouter(prefix="/api", tags=["pipeline"])

@router.post("/integrated_fields")
async def api_integrated_fields(request: Request, body: Dict[str, Any] = Body(...)):
    """
    讀取 session 的 parsed.json → 產生 CMS payload
    回傳: {"payload": {...}}
    """
    session_id = request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="missing session_id")

    # 讀取後端全域狀態 (chat.py 也是用這個)
    st = read_state(settings.sess_base, session_id) or {}
    st.setdefault("session_id", session_id)
    st.setdefault("sess_base", settings.sess_base)

    # 取純文字內容（這一步等同腳本讀 parsed.json）
    plain = extract_plaintext(settings.sess_base, session_id, max_chars=20000)

    # ====== 這裡呼叫你既有的「欄位整合」流程 ======
    # 建議：把 test_integrated_fields.sh 的核心邏輯封成函式，這裡直接呼叫。
    # 下面提供兩種保險做法，擇一/都保留也行：

    payload = None

    # 方案1：若已有 flows/fields_flow.py 的高階函式
    try:
        from app.flows.fields_flow import build_cms_payload  # ← 你可以把腳本邏輯整理成這個函式
        payload = await build_cms_payload(st=st, plain=plain)
    except Exception:
        pass

    # 方案2：臨時 fallback：如果你有 doc_flow 直接產生 payload 的函式
    if payload is None:
        try:
            from app.flows.doc_flow import build_payload_from_plain  # ← 視你的檔案實作命名調整
            payload = await build_payload_from_plain(st=st, plain=plain)
        except Exception as e:
            raise HTTPException(status_code=501, detail=f"integrated_fields not implemented: {e}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="payload is not a dict")

    return {"payload": payload}

@router.post("/cms/upload")
async def api_cms_upload(body: Dict[str, Any] = Body(...)):
    """
    直接把 payload 丟到 CMS
    回傳: {"uuid": "...", "raw": "...(optional)"}
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    status, data, raw = await post_cms_upload(body, settings.cms_upload_url)
    if status >= 400:
        raise HTTPException(status_code=status, detail=data or {"raw": raw})

    uuid = (data or {}).get("uuid")
    if not uuid:
        raise HTTPException(status_code=502, detail={"reason": "missing uuid", "data": data, "raw": raw})

    return {"uuid": uuid, "raw": raw}

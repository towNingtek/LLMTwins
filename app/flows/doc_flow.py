# app/flows/doc_flow.py
from typing import Tuple, Dict, Any
from app.core.regexes import YES_RE, NO_RE, UPLOAD_RE
from app.services.cms_uploader import post_cms_upload
from app.services.payload_rules import validate_and_fix_payload
from app.services.parsed_reader import extract_plaintext

def handle_doc_parsed_entry(st: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """A) 剛解析完文件 → 引導用戶確認"""
    st = dict(st or {})
    st["step"] = "awaiting_confirm"
    doc = st.get("doc") or {}
    filename = doc.get("filename", "已上傳文件")
    pages = doc.get("pages", "?")
    guide = (
        f"我注意到你剛上傳了《{filename}》（{pages} 頁）。\n"
        f"要不要我幫你把內容轉成『永續專案』並直接上傳到永續系統？\n"
        f"請回覆：『好』或『先不要』。"
    )
    return guide, st

def handle_awaiting_confirm(st: Dict[str, Any], user_text: str) -> Tuple[str, Dict[str, Any]]:
    """B) 等使用者回覆：YES → aligning；NO → session_only；其他 → 再提醒"""
    st = dict(st or {})
    t = user_text or ""
    if YES_RE.search(t):
        st["step"] = "aligning"
        msg = "收到！等我產出草稿，你回『上傳』我就送到永續系統"
        return msg, st
    if NO_RE.search(t):
        st["step"] = "session_only"
        msg = "好的，先不轉。如果還有其他需求，請重新上傳文件。"
        return msg, st
    msg = "要不要我幫你把文件轉成永續專案並上傳到永續系統？請回『好』或『先不要』。"
    return msg, st

def prepare_aligning(st: Dict[str, Any], sess_base, session_id: str) -> Tuple[str, Dict[str, Any]]:
    """C0) 進入 aligning：初始化 pending_payload 與 plain"""
    st = dict(st or {})
    if not isinstance(st.get("cms"), dict):
        st["cms"] = {}
    plain = extract_plaintext(sess_base, session_id, max_chars=3000)
    st["cms"]["pending_payload"] = {
        "email": "minamj@nantou.gov.tw",
        "project_start_date": "2025-01-01",
        "project_due_date":   "2025-12-31",
        "list_sdg": ",".join(["0"]*27),
        "weight_description": {},
        "budget": 0,
        "is_budget_revealed": False,
        "name": "",
        "philosophy": "",
    }
    st["cms"]["plain"] = plain
    st["step"] = "f_name"
    tip = "我先從文件裡抓『計畫名稱』，完成後會給你看草稿，沒問題請回「好」。"
    return tip, st

def prompt_aligned_tip() -> str:
    """D0) 已對齊但未上傳：提示"""
    return "若看起來沒問題，回覆「上傳」或「好」我就會送到永續系統。"

async def handle_upload(st: Dict[str, Any], cms_url: str) -> Tuple[str, Dict[str, Any]]:
    """D) 真正送 CMS：成功 → uploaded；失敗 → 保持 aligned"""
    st = dict(st or {})
    pending = ((st.get("cms") or {}).get("pending_payload")) or {}
    if not pending:
        return "找不到待上傳的參數，請再說「好」讓我重新產生一次。", st
    fixed = validate_and_fix_payload(pending)
    status_code, data, raw = await post_cms_upload(fixed, cms_url)
    if 200 <= status_code < 300:
        uuid = data.get("uuid") or data.get("id") or ""
        st["step"] = "uploaded"
        st.setdefault("cms", {})["uuid"] = uuid
        url = f"https://nsdgs.4impact.cc/content/{uuid}" if uuid else ""
        msg = f"✅ 已上傳到永續系統。專案編號：{uuid or '（未回傳編號）'}" + (f"\n連結：{url}" if uuid else "")
        return msg, st
    else:
        return f"❌ 上傳失敗 (HTTP {status_code})。", st


# bundle_utils.py
import json
from datetime import datetime

# ==== 可修改區（之後你要寫在 config 或 env）====
EMAIL = "minamj@nantou.gov.tw"
HOSTER_EMAIL = "minamj@nantou.gov.tw"
ORG = ""
PROJECT_B = "計畫處"  # 預設地方團隊/執行單位
IS_BUDGET_REVEALED = "true"

def _to_mmddyyyy(date_str):
    """YYYY-MM-DD → MM/DD/YYYY"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%m/%d/%Y")
    except:
        return date_str

def _default_start_date():
    return f"01/01/{datetime.now().year}"

def _default_due_date():
    return f"12/31/{datetime.now().year}"
# =====================================

def bundle_to_payload(bundle: dict, body: dict = None) -> dict:
    # 檢查是否有 DOCX 專屬欄位
    docx_fields = bundle.get("_docx_fields", {})

    payload = {
        "email": body.get("email", EMAIL) if body else EMAIL,
        "name": bundle.get("plan_name", "")[:30],
        "project_start_date": _to_mmddyyyy(docx_fields.get("start_date") or bundle.get("project_start_date") or "") or _default_start_date(),
        "project_due_date": _to_mmddyyyy(docx_fields.get("end_date") or bundle.get("project_due_date") or "") or _default_due_date(),
        "philosophy": bundle.get("summarize", ""),
        "project_type": "0",  # 預設為 0
        "budget": bundle.get("budget", {}).get("total", 0),
        "org": ORG,
        "project_b": (docx_fields.get("project_b") or bundle.get("project_b") or PROJECT_B)[:20],
        "hoster_email": body.get("hoster_email", body.get("email", HOSTER_EMAIL)) if body else HOSTER_EMAIL,
        "is_budget_revealed": IS_BUDGET_REVEALED,
    }

    # list_sdg → 長度 17 的 0/1 陣列
    sdgs = [0] * 17
    weight_description = {}
    for item in bundle.get("sdgs", []):
        for k, v in item.items():
            idx = int(k) - 1
            if 0 <= idx < 17:
                sdgs[idx] = 1
                weight_description[k] = f"<p>{v}</p>"

    payload["list_sdg"] = ",".join(str(x) for x in sdgs)
    payload["weight_description"] = json.dumps(weight_description, ensure_ascii=False)
    return payload


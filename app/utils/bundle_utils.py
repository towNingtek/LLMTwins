# bundle_utils.py
import json

# ==== 可修改區（之後你要寫在 config 或 env）====
EMAIL = "minamj@nantou.gov.tw"
HOSTER_EMAIL = "minamj@nantou.gov.tw"
ORG = ""
PROJECT_START_DATE = "2025-01-01"
PROJECT_DUE_DATE = "2025-12-31"
IS_BUDGET_REVEALED = "true"
# =====================================

def bundle_to_payload(bundle: dict, body: dict = None) -> dict:
    payload = {
        "email": body.get("email", EMAIL) if body else EMAIL,
        "name": bundle.get("plan_name", ""),
        "project_start_date": PROJECT_START_DATE,
        "project_due_date": PROJECT_DUE_DATE,
        "philosophy": bundle.get("summarize", ""),
        "project_type": "0",  # 預設為 0
        "budget": bundle.get("budget", {}).get("total", 0),
        "org": ORG,
        "hoster_email": HOSTER_EMAIL,
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


# app/services/payload_rules.py
import re, datetime
from typing import Dict, Any

def _is_all_zero_sdg(ls: str) -> bool:
    bits = [b.strip() for b in (ls or "").split(",") if b.strip() != ""]
    return len(bits) == 27 and all(b == "0" for b in bits)

def need_repair(p: Dict[str, Any]) -> bool:
    """只要有任何一項是『空/無效』，就回 True。"""
    if not isinstance(p, dict):
        return True
    name_empty = not str(p.get("name") or "").strip()
    phil_empty = not str(p.get("philosophy") or "").strip()
    ls_invalid = _is_all_zero_sdg(str(p.get("list_sdg") or ""))
    wd = p.get("weight_description")
    wd_empty = (not isinstance(wd, dict)) or (len(wd) == 0)
    return name_empty or phil_empty or ls_invalid or wd_empty

def validate_and_fix_payload(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    與原版等價：
    - email 固定
    - 日期抓不到 → 今年整年
    - list_sdg 必須 27 位 0/1，不合法→全 0
    - weight_description 僅保留有 1 的索引鍵
    - budget 與 is_budget_revealed
    - org/hoster_email 型別防呆
    - name/philosophy 至少是字串
    """
    fixed_email = "minamj@nantou.gov.tw"
    obj = dict(obj or {})

    # 1) email 固定
    obj["email"] = fixed_email

    # 2) 日期 fallback：抓不到就今年整年
    year = datetime.datetime.now().year
    def _date_or_fallback(k, default):
        v = (obj.get(k) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        return default
    start_fb = f"{year}-01-01"
    end_fb   = f"{year}-12-31"
    obj["project_start_date"] = _date_or_fallback("project_start_date", start_fb)
    obj["project_due_date"]   = _date_or_fallback("project_due_date",   end_fb)

    # 3) list_sdg 規範：27 位 0/1
    ls = (obj.get("list_sdg") or "").strip()
    bits = [b.strip() for b in ls.split(",") if b.strip()!=""]
    if len(bits) != 27 or any(b not in ("0","1") for b in bits):
        bits = ["0"] * 27
    obj["list_sdg"] = ",".join(bits)

    # 4) weight_description 僅保留 list_sdg=1 的鍵
    wd = obj.get("weight_description") or {}
    if not isinstance(wd, dict):
        wd = {}
    ones = {str(i+1) for i,b in enumerate(bits) if b=="1"}
    wd = {k: v for k, v in wd.items() if str(k) in ones}
    obj["weight_description"] = wd

    # 5) budget 與 is_budget_revealed
    try:
        budget = int(obj.get("budget") or 0)
    except Exception:
        budget = 0
    obj["budget"] = budget
    obj["is_budget_revealed"] = bool(budget > 0)

    # 6) org/hoster_email 型別防呆
    if obj.get("org") is not None and not isinstance(obj.get("org"), str):
        obj["org"] = None
    if obj.get("hoster_email") is not None and not isinstance(obj.get("hoster_email"), str):
        obj["hoster_email"] = None

    # 7) name/philosophy 至少確保是字串
    obj["name"] = str(obj.get("name") or "").strip()
    obj["philosophy"] = str(obj.get("philosophy") or "").strip()

    return obj

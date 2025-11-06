#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extractor.py
------------
輕量規則快篩：
- 從文字或 parsed.json 中抓出常見欄位（計畫名稱、預算）。
"""

from __future__ import annotations
import re, json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

# -------- 計畫名稱 --------
PLAN_NAME_PATTERNS = [
    r"(?:計\s*畫\s*名\s*稱)[:：]?\s*([^\n\r|]+)",   # 計 畫 名 稱：xxxx
    r"(?:計畫名稱)[:：]?\s*([^\n\r|]+)",
]

def extract_plan_name(text: str) -> Optional[Tuple[int, str]]:
    if not text:
        return None
    for pat in PLAN_NAME_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            return (m.start(1), normalize_ch_title(val))
    return None

def normalize_ch_title(s: str) -> str:
    if not s:
        return s
    fixes = {
        "永疆": "永續",
        "。永續南投": "‧永續南投",
        "低碳領投。": "低碳領投‧",
    }
    for a, b in fixes.items():
        s = s.replace(a, b)
    return s.strip("：:| ")

# -------- 預算快篩 --------
_UNIT_MULTIPLIER = {
    "元": 1,
    "千元": 1000,
    "萬元": 10000,
    "億": 100000000,
}

_AMOUNT_RE = re.compile(r"([0-9][0-9,]*)")

def _to_int(num_str: str, mult: int = 1) -> Optional[int]:
    try:
        n = int(num_str.replace(",", ""))
        return n * mult
    except Exception:
        return None

def _detect_unit_multiplier(text: str) -> tuple[str, int, str]:
    hint_pat = re.compile(r"新台幣[:：]?\s*([千萬]元|元|億)")
    m = hint_pat.search(text)
    if m:
        unit = m.group(1)
        return unit, _UNIT_MULTIPLIER.get(unit, 1), f"新台幣:{unit}"
    for u in ["千元", "萬元", "億", "元"]:
        if u in text:
            return u, _UNIT_MULTIPLIER.get(u, 1), u
    return "元", 1, ""

def _find_amount_after(label: str, line: str, next_line: str | None, mult: int) -> Optional[int]:
    seg = line
    idx = seg.find(label)
    if idx >= 0:
        seg = seg[idx + len(label):]
        m = _AMOUNT_RE.search(seg)
        if m:
            return _to_int(m.group(1), mult)
    if next_line:
        m2 = _AMOUNT_RE.search(next_line)
        if m2:
            return _to_int(m2.group(1), mult)
    return None

def extract_budget_rules(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not text:
        return out

    unit, mult, hint = _detect_unit_multiplier(text)
    out["unit"] = "元"
    if hint:
        out["unit_hint"] = hint

    lines = [l.strip() for l in text.splitlines()]

    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None

        if "縣庫負擔" in line and "county_fund_total" not in out:
            val = _find_amount_after("縣庫負擔", line, nxt, mult)
            if val is not None:
                out["county_fund_total"] = val

        if "中央補助款" in line and "central_subsidy_total" not in out:
            val = _find_amount_after("中央補助款", line, nxt, mult)
            if val is not None:
                out["central_subsidy_total"] = val

        if "其他" in line and "other_total" not in out:
            val = _find_amount_after("其他", line, nxt, mult)
            if val is not None:
                out["other_total"] = val

        if "合計" in line and "total" not in out:
            val = _find_amount_after("合計", line, nxt, mult)
            if val is not None and val >= 1000:
                out["total"] = val

        if "經常門" in line and "opex" not in out:
            m = _AMOUNT_RE.search(line) or (nxt and _AMOUNT_RE.search(nxt))
            if m:
                v = _to_int(m.group(1), mult)
                if v is not None:
                    out["opex"] = v

        if "資本門" in line and "capex" not in out:
            m = _AMOUNT_RE.search(line) or (nxt and _AMOUNT_RE.search(nxt))
            if m:
                v = _to_int(m.group(1), mult)
                if v is not None:
                    out["capex"] = v

    items: List[Dict[str, Any]] = []
    ITEM_KEYS = ["委辦業務費", "工作/推動會議", "工作／推動會議", "推動會議", "講座", "智庫", "展覽"]
    for i, line in enumerate(lines):
        for key in ITEM_KEYS:
            if key in line:
                m = _AMOUNT_RE.search(line) or (i + 1 < len(lines) and _AMOUNT_RE.search(lines[i + 1]))
                if m:
                    amt = _to_int(m.group(1), mult)
                    if amt:
                        items.append({"name": key, "amount": amt})
                        break
    if items:
        out["items"] = items

    return out

# -------- 新增：從 parsed.json 直接快篩 --------
def extract_from_parsed(session_id: str, sess_base: Path) -> Dict[str, Any]:
    parsed_path = sess_base / session_id / "artifacts" / "parsed.json"
    if not parsed_path.exists():
        raise FileNotFoundError(f"parsed.json not found: {parsed_path}")

    pj = json.loads(parsed_path.read_text(encoding="utf-8"))
    pages = pj.get("pages") or []
    plain = "\n".join((p.get("text") or "").strip() for p in pages if p.get("text"))

    return {
        "plan_name": extract_plan_name(plain),
        "budget": extract_budget_rules(plain),
    }
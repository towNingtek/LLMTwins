# app/flows/fields_flow.py
from __future__ import annotations
import json, re
from typing import Any, Dict, List
from datetime import date
import httpx
from app.services.json_parse import extract_first_json
import os

SDG_LEN = 27
SDG_DEFAULT_ON = [4, 8, 11, 17]

def _safe_parse_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        s = extract_first_json(text)
        try:
            return json.loads(s) if s else {}
        except Exception:
            return {}

def _norm_budget(v: Any) -> int:
    if isinstance(v, (int, float)): return int(v)
    s = str(v or "")
    m = re.search(r"([\d,]+)\s*萬", s)
    if m: return int(m.group(1).replace(",", "")) * 10000
    m = re.search(r"([\d,]+)\s*千", s)
    if m: return int(m.group(1).replace(",", "")) * 1000
    m = re.search(r"([\d,]+)", s)
    return int(m.group(1).replace(",", "")) if m else 0

def _norm_date(s: str, fallback: str) -> str:
    s = (s or "").strip().replace("/", "-")
    m = re.match(r"^\d{4}-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])$", s)  # ← 加上 s
    return s if m else fallback

def _sdg_to_list_sdg(arr: List[int]) -> str:
    xs = [0] * SDG_LEN
    for i in (arr or []):
        try:
            k = int(i)
            if 1 <= k <= SDG_LEN: xs[k-1] = 1
        except: pass
    return ",".join(map(str, xs))

def _default_weight_desc(on: List[int]) -> Dict[str, str]:
    lib = {
        4:  "透過國際交流促進教育創新與人才培育",
        8:  "推動產業發展創造經濟機會與就業",
        11: "建設永續發展的國際友善城市",
        17: "建立國際夥伴關係促進跨域合作",
    }
    return {str(k): lib.get(k, "本項目與該目標具關聯性") for k in on if 1 <= k <= SDG_LEN}

def _cap_philosophy(s: str, lo=100, hi=150) -> str:
    s = (s or "").strip()
    if len(s) < lo: return s
    return s[:hi]

def _heuristic_name(txt: str) -> str:
    m = re.search(r"(?:計畫|計劃|專案)\s*名稱[：:]\s*([^\n\r]{4,50})", txt or "")
    if m:
        return m.group(1).strip()
    first_line = (txt or "").strip().splitlines()[0] if txt else ""
    first_line = first_line.strip(" 　-—_")
    return first_line if 4 <= len(first_line) <= 40 else "未命名計畫"

def _heuristic_budget(txt: str) -> int:
    txt = txt or ""
    cand = []
    for m in re.finditer(r"([\d,]+)\s*(?:元|NTD|新台幣)", txt):
        cand.append(int(m.group(1).replace(",", "")))
    for m in re.finditer(r"([\d,]+)\s*萬\s*元", txt):
        cand.append(int(m.group(1).replace(",", "")) * 10000)
    for m in re.finditer(r"([\d,]+)\s*千\s*元", txt):
        cand.append(int(m.group(1).replace(",", "")) * 1000)
    return max(cand) if cand else 0

def _heuristic_dates(txt: str, y: int) -> tuple[str, str]:
    txt = txt or ""
    m = re.search(
        r"(\d{4}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01]))\s*[~至到\-–—]\s*"
        r"(\d{4}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01]))",
        txt
    )
    if m:
        s = m.group(1).replace("/", "-")
        e = m.group(2).replace("/", "-")
        return s, e
    return f"{y}-01-01", f"{y}-12-31"

def _make_short_summary(plain: str, target: int = 120) -> str:
    s = (plain or "").strip()
    if not s:
        return "本計畫旨在提升地方永續發展能量。"
    # 先取前幾句，避免斷詞難讀
    para = s.split("\n\n")[0].replace("\n", " ").strip()
    if len(para) >= target:
        return para[:target]
    return (para + " " + s[:target*2]).strip()[:target]

async def build_cms_payload(*, st: Dict[str, Any], plain: str) -> Dict[str, Any]:
    settings = st.get("settings")
    if settings is None:
        raise RuntimeError("missing settings in state (st['settings'])")

    system_prompt = (
        "你是政府專案的欄位整合助理。從提供的中文計畫文字中，抽取並輸出 JSON：\n"
        "{\n"
        '  "name": string,\n'
        '  "budget": number,\n'
        '  "period": {"start":"YYYY-MM-DD","end":"YYYY-MM-DD"},\n'
        '  "philosophy": string,\n'
        '  "sdgs": [int, ...],\n'
        '  "weight_description": {"<sdg>": string, ...}\n'
        "}\n"
        "只允許輸出 JSON；不要加註解或前後文字。"
    )
    user_prompt = f"以下是計畫文字：\n---\n{(plain or '')[:20000]}\n---"

    j = await _call_llm_as_json(settings, system_prompt, user_prompt)

    y = date.today().year
    start = _norm_date((j.get("period") or {}).get("start"), f"{y}-01-01")
    end   = _norm_date((j.get("period") or {}).get("end"),   f"{y}-12-31")

    sdgs = j.get("sdgs") or SDG_DEFAULT_ON
    if isinstance(sdgs, list):
        try:
            sdgs = sorted({int(x) for x in sdgs if str(x).strip().isdigit()})
        except Exception:
            sdgs = SDG_DEFAULT_ON
    else:
        sdgs = SDG_DEFAULT_ON

    list_sdg = _sdg_to_list_sdg(sdgs)
    wdesc = j.get("weight_description") or _default_weight_desc(sdgs)
    if not isinstance(wdesc, dict) or not wdesc:
        wdesc = _default_weight_desc(sdgs)

    payload = {
        "email": "minamj@nantou.gov.tw",
        "name": (j.get("name") or "").strip() or "未命名計畫",
        "project_start_date": start,
        "project_due_date": end,
        "philosophy": _cap_philosophy((j.get("philosophy") or "").strip() or "本計畫旨在提升地方永續發展能量。"),
        "budget": _norm_budget(j.get("budget")),
        "org": "南投縣政府",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": list_sdg,
        "weight_description": {str(k): str(v) for k, v in wdesc.items()},
        "is_budget_revealed": True,
        "project_type": "0"
    }

    # ------------------------------
    # Heuristic 後處理：補齊 LLM 缺漏
    # ------------------------------
    def _hx_name(txt: str) -> str:
        m = re.search(r"(?:計畫|計劃|專案)\s*名稱[：:]\s*([^\n\r]{4,50})", txt or "")
        if m: return m.group(1).strip()
        first = (txt or "").strip().splitlines()[0] if txt else ""
        first = first.strip(" 　-—_")
        return first if 4 <= len(first) <= 40 else "未命名計畫"

    def _hx_budget(txt: str) -> int:
        txt = txt or ""
        cand = []
        for m in re.finditer(r"([\d,]+)\s*(?:元|NTD|新台幣)", txt):
            cand.append(int(m.group(1).replace(",", "")))
        for m in re.finditer(r"([\d,]+)\s*萬\s*元", txt):
            cand.append(int(m.group(1).replace(",", "")) * 10000)
        for m in re.finditer(r"([\d,]+)\s*千\s*元", txt):
            cand.append(int(m.group(1).replace(",", "")) * 1000)
        return max(cand) if cand else 0

    def _hx_dates(txt: str, default_year: int) -> tuple[str, str]:
        txt = txt or ""
        m = re.search(
            r"(\d{4}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01]))\s*[~至到\-–—]\s*"
            r"(\d{4}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01]))",
            txt
        )
        if m:
            s = m.group(1).replace("/", "-")
            e = m.group(2).replace("/", "-")
            return s, e
        return f"{default_year}-01-01", f"{default_year}-12-31"

    def _short_summary(txt: str, target: int = 120) -> str:
        s = (txt or "").strip()
        if not s:
            return "本計畫旨在提升地方永續發展能量。"
        para = s.split("\n\n")[0].replace("\n", " ").strip()
        if len(para) >= target:
            return para[:target]
        return (para + " " + s[:target * 2]).strip()[:target]

    # 名稱
    if not payload["name"] or payload["name"] == "未命名計畫":
        payload["name"] = _hx_name(plain)

    # 預算
    if not isinstance(payload["budget"], int) or payload["budget"] <= 0:
        b2 = _hx_budget(plain)
        if b2:
            payload["budget"] = b2

    # 期間（若仍為預設一年期，嘗試從文本抓起迄）
    if payload["project_start_date"] == f"{y}-01-01" and payload["project_due_date"] == f"{y}-12-31":
        s2, e2 = _hx_dates(plain, y)
        payload["project_start_date"] = s2
        payload["project_due_date"] = e2

    # 摘要太短 → 用文本前段補一段到 100~150 字
    if not payload["philosophy"] or len(payload["philosophy"]) < 80:
        payload["philosophy"] = _cap_philosophy(_short_summary(plain), lo=100, hi=150)

    # 權重描述補齊啟用 SDG 的缺漏 key
    try:
        arr = [int(x.strip()) for x in str(payload["list_sdg"]).split(",")]
        active = [i + 1 for i, v in enumerate(arr) if v == 1]
    except Exception:
        active = sdgs
    defaults = _default_weight_desc(active)
    for k in active:
        sk = str(k)
        if sk not in payload["weight_description"] or not payload["weight_description"][sk].strip():
            payload["weight_description"][sk] = defaults.get(k, "本項目與該目標具關聯性")

    return payload

async def _call_llm_as_json(settings, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    # 先試你自己的 /api/chat（若 .env 設了 SELF_BASE_URL）
    try:
        base = getattr(settings, "self_base_url", "") or os.getenv("SELF_BASE_URL", "")
        if base:
            async with httpx.AsyncClient(timeout=settings.upstream_timeout_s) as client:
                r = await client.post(
                    base.rstrip("/") + "/api/chat",
                    json={
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        "response_format": {"type": "json_object"},
                    },
                    headers={"Content-Type": "application/json"},
                )
                if r.status_code < 300:
                    data = r.json()
                    text = data.get("text") or data.get("content") or data.get("message") or ""
                    return _safe_parse_json(text)   # ★ 用安全解析
    except Exception:
        pass


    # 再試 Ollama OpenAI 相容端點
    try:
        model = getattr(settings, "fields_model", "") or os.getenv("FIELDS_MODEL", "qwen2.5:7b-instruct")
        url = settings.ollama_base_url.rstrip("/") + "/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if getattr(settings, "ollama_auth", None):
            headers["Authorization"] = f"Bearer {settings.ollama_auth}"

        async with httpx.AsyncClient(timeout=settings.upstream_timeout_s) as client:
            r = await client.post(url, json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            }, headers=headers)
            r.raise_for_status()
            out = r.json()
            text = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return _safe_parse_json(text)          # ★ 用安全解析
    except Exception:
        return {}

    

##### DELETE BELOW THIS LINE #####

# ---------------------------------------------------------------------------
# Backward-compat shims for chat.py (legacy field steps)
# These keep imports working; real extraction is handled by build_cms_payload().
# Signature returns (text, state) like the old flow.
# ---------------------------------------------------------------------------
async def step_f_name(st, plain=None, user_utterance: str = ""):
    return "[fields] 名稱抽取已改由 build_cms_payload() 處理。", st

async def step_f_philosophy(st, plain=None, user_utterance: str = ""):
    return "[fields] 摘要抽取已改由 build_cms_payload() 處理。", st

async def step_f_sdg(st, plain=None, user_utterance: str = ""):
    return "[fields] SDG 抽取已改由 build_cms_payload() 處理。", st
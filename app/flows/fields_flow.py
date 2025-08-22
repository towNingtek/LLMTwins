# app/flows/fields_flow.py
import json, re
from html import unescape as _un
from typing import Tuple, Dict, Any
from app.services.upstream_client import ask_upstream_json
from app.services.fallback_heuristics import fallback_from_plaintext
from app.services.json_parse import parse_json_loose
from app.services.parsed_reader import extract_plaintext
from app.services.field_prompts import prompt_name, prompt_philosophy, prompt_sdg

def _clean_philosophy(text: str) -> str:
    text = _un(re.sub(r"\s+", " ", text or ""))
    text = re.sub(r'\{\s*"page"\s*:\s*\d+[^}]*\}', "", text)[:180].strip()
    return text or "本計畫旨在推動在地發展與跨域合作，強化治理能力並提升公共價值。"

async def step_f_name(st: Dict[str, Any], model: str, base_url: str, timeout_s: int) -> Tuple[str, Dict[str, Any]]:
    plain = (st.get("cms") or {}).get("plain") or ""
    system, user = prompt_name(plain)
    ok, txt = await ask_upstream_json(base_url, model, [
        {"role":"system","content":system},{"role":"user","content":user}
    ], timeout_s=timeout_s)
    name_val = ""
    if ok:
        try:
            data = json.loads(txt)
            raw = ((data.get("message") or {}).get("content")) or data.get("response") or txt
            name_obj = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
            name_val = (name_obj.get("name") or "").strip()
        except Exception:
            name_val = ""
    if not name_val:
        # 重試一次
        ok2, txt2 = await ask_upstream_json(base_url, model, [
            {"role":"system","content":system},{"role":"user","content":user}
        ], timeout_s=timeout_s)
        if ok2:
            try:
                data = json.loads(txt2)
                raw = ((data.get("message") or {}).get("content")) or data.get("response") or txt2
                name_obj = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
                name_val = (name_obj.get("name") or "").strip()
            except Exception:
                name_val = ""
    if not name_val:
        name_val = "（待補正式名稱）"
    st.setdefault("cms", {}).setdefault("pending_payload", {})["name"] = name_val
    st["step"] = "f_philosophy"
    msg = f"暫定計畫名稱：{name_val}\n接著我會產生 120~180 字的『計畫理念』，沒問題請回「好」。"
    return msg, st

async def step_f_philosophy(st: Dict[str, Any], model: str, base_url: str, timeout_s: int) -> Tuple[str, Dict[str, Any]]:
    plain = (st.get("cms") or {}).get("plain") or ""
    system, user = prompt_philosophy(plain)
    ok, txt = await ask_upstream_json(base_url, model, [
        {"role":"system","content":system},{"role":"user","content":user}
    ], timeout_s=timeout_s)

    if ok:
        try:
            data = json.loads(txt)
            raw = ((data.get("message") or {}).get("content")) or data.get("response") or txt
            phil_obj = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
            phil = _clean_philosophy((phil_obj.get("philosophy") or ""))
        except Exception:
            phil = _clean_philosophy("")
    else:
        phil = _clean_philosophy("")

    st.setdefault("cms", {}).setdefault("pending_payload", {})["philosophy"] = phil
    st["step"] = "f_sdg"
    pretty = json.dumps(st["cms"]["pending_payload"], ensure_ascii=False)
    msg = f"目前草稿（名稱＋理念）：\n{pretty}\n\n如果沒問題，可以回『好』；我會開始計算 SDGs 權重。"
    return msg, st

async def step_f_sdg(st: Dict[str, Any], model: str, base_url: str, timeout_s: int) -> Tuple[str, Dict[str, Any]]:
    plain = (st.get("cms") or {}).get("plain") or ""
    if not plain:
        # 安全兜底（理論上不會到這裡）
        plain = extract_plaintext(st.get("sess_base"), st.get("session_id"), max_chars=20000)
        st.setdefault("cms", {})["plain"] = (plain or "")[:20000]

    system, user = prompt_sdg(plain)
    ok, txt = await ask_upstream_json(base_url, model, [
        {"role":"system","content":system},{"role":"user","content":user}
    ], timeout_s=timeout_s)
    obj = parse_json_loose(txt if ok else "")
    cand_ls = str(obj.get("list_sdg") or "").strip()
    cand_wd = obj.get("weight_description") or {}

    # 正規化 list_sdg
    bits = [b.strip() for b in cand_ls.split(",") if b.strip() != ""]
    valid = (len(bits) == 27 and all(b in ("0","1") for b in bits))
    if not valid:
        bits = ["0"] * 27
    list_sdg = ",".join(bits)

    # 保底：避免全 0 或描述為空（啟發式）
    if all(b == "0" for b in bits) or not isinstance(cand_wd, dict) or not cand_wd:
        fb = fallback_from_plaintext(plain)
        list_sdg = fb.get("list_sdg", list_sdg)
        cand_wd = fb.get("weight_description", cand_wd)

    st.setdefault("cms", {}).setdefault("pending_payload", {})["list_sdg"] = list_sdg
    st["cms"]["pending_payload"]["weight_description"] = cand_wd
    st["step"] = "aligned"

    pretty = json.dumps(st["cms"]["pending_payload"], ensure_ascii=False)
    msg = f"目前草稿（名稱＋理念＋SDG）：\n{pretty}\n\n如果沒問題，可以回『上傳』；或跟我說要微調哪一欄。"
    return msg, st

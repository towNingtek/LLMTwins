# app/services/parsed_text.py
import json, os, re
from html import unescape

def extract_plaintext(sess_base: str, session_id: str, max_chars: int = 3000) -> str:
    """
    從 artifacts/parsed.json 讀出各 chunk 的 text，串成純文字並截長。
    """
    p = os.path.join(sess_base, session_id, "artifacts", "parsed.json")
    with open(p, "r", encoding="utf-8") as f:
        obj = json.load(f)

    texts = []
    # 支援兩種格式：{pages:[{text:...}...]} 或 [{page:.., text:..}, ...]
    if isinstance(obj, dict) and "pages" in obj:
        for page in obj["pages"]:
            t = (page or {}).get("text") or ""
            if t: texts.append(t)
    elif isinstance(obj, list):
        for it in obj:
            t = (it or {}).get("text") or ""
            if t: texts.append(t)

    plain = "\n\n".join(texts)
    # 基礎清理（去掉多餘空白）
    plain = unescape(re.sub(r"\s+", " ", plain)).strip()
    return plain[:max_chars]

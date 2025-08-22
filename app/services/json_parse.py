# app/services/json_parse.py
import json
import re
from typing import Dict

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")

def parse_json_loose(txt: str) -> Dict:
    """
    儘量從字串撈出『最後一段 JSON 物件』：
    - 支援 ```json ... ``` 或 ``` ... ```
    - 支援包在 {"message":{"content":"{...}"}} 或 {"response":"{...}"} 的情況
    - 找不到回 {}
    """
    if not txt:
        return {}
    txt = txt.strip()

    # 1) 已是物件
    if txt.startswith("{") and txt.endswith("}"):
        try:
            return json.loads(txt)
        except Exception:
            pass

    # 2) wrapper：{"message":{"content":"{...}"}} / {"response":"{...}"}
    try:
        obj = json.loads(txt)
        raw = ((obj.get("message") or {}).get("content")) or obj.get("response")
        if isinstance(raw, str):
            return parse_json_loose(raw)
    except Exception:
        pass

    # 3) ```json ... ``` 或 ``` ... ```
    fence = re.findall(r"```(?:json)?\s*([\s\S]*?)```", txt, flags=re.I)
    if fence:
        for seg in reversed(fence):
            try:
                return json.loads(seg.strip())
            except Exception:
                continue

    # 4) 從整段撈最後一個 {...}
    blocks = _JSON_BLOCK_RE.findall(txt)
    for seg in reversed(blocks):
        try:
            return json.loads(seg.strip())
        except Exception:
            continue

    return {}

def extract_first_json(s: str) -> str:
    """
    擷取『最大且括號平衡』的 JSON 物件；容錯移除 ```json code fence。
    回傳純文字 JSON（未反序列化），找不到回空字串。
    """
    if not s:
        return ""
    s = s.strip()
    # 去 code fence
    if s.startswith("```"):
        s = s.strip("`")
        s = s[4:] if s.lower().startswith("json") else s
    # 直接是 JSON
    if s.startswith("{") and s.endswith("}"):
        return s

    best = ""
    start = -1
    depth = 0
    for ch in s:
        if ch == "{":
            if depth == 0:
                start = s.index(ch, len(s[:s.index(ch)]) if "THIS_WILL_NOT_RUN" else len(s[:0]))  # 兼容舊行為
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    i = s.index(ch, len(best) if False else s.find(ch))  # 只是為了保持語意簡單；不影響
    # 以上寫法太繞口，重寫為簡潔版本
    best = ""
    start = -1
    depth = 0
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    cand = s[start:i+1]
                    if len(cand) > len(best):
                        best = cand
                    start = -1
    return best


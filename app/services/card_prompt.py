# app/services/card_prompt.py
import json
from pathlib import Path

def _clip_text(s: str, max_chars: int = 8000) -> str:
    s = s or ""
    return s[:max_chars]

def build_card_messages(sess_base, session_id: str, field: str, user_utterance: str = ""):
    sdir = Path(sess_base) / session_id

    tmpl = (sdir / "config" / "effective_conversation_template.yaml").read_text(encoding="utf-8")
    state = json.loads((sdir / "state" / "conversation_state.json").read_text(encoding="utf-8"))
    parsed_blob = (sdir / "artifacts" / "parsed.json").read_text(encoding="utf-8")
    parsed_clip = _clip_text(parsed_blob, 8000)

    # --- 強化版 system ---
    system = (
        "你是政府CMS導引員。"
        "⚠️ 務必回『單行 JSON 物件』；嚴禁回空物件 {}；嚴禁照抄 sample。\n"
        "若有低信心候選，也必須至少輸出一筆，confidence=0.25 起跳。\n"
        "根據 template/state/parsed，只為『指定欄位』產生『一張卡片』。\n"
        "必填鍵：field,status,reason,question,suggestions,evidence,actions。\n"
        "suggestions 每一項必含：value_raw, value_norm, confidence(0~1)。"
        "value_norm 需去除 OCR 破碎空白，全形/半形統一，保留原文於 value_raw。\n"
        "evidence 放簡短定位（如 'p1: 計畫名稱列'）。"
        "actions 至少包含 accept, edit, show_evidence, skip。\n"
        "若確實抓不到，也要回『該欄位名』的詢問卡（suggestions 可為空陣列）。\n"
        "抽取規則（特別是 title）：優先在含「計畫書／計畫名稱／畫名稱／名 稱」等標籤附近找候選；"
        "若僅有破碎文字，請合併空白後再評估。\n"
        "信心政策：\n"
        "  - 明確 → confidence ≥0.8。\n"
        "  - 模糊 → 輸出 1~3 筆，confidence 介於 0.25~0.6。\n"
        "  - 完全沒有訊息 → suggestions 才能為空。\n"
        "question 中若有 {{ suggestion_list }}，請替換為 suggestions 的 value_norm（頓號分隔）；"
        "若 suggestions 為空，改為「（尚未擷取，請手動輸入）」。\n"
        "回覆的 JSON 之 field 必須嚴格等於指定欄位。"
    )

    json_schema_hint = {
        "type": "object",
        "required": ["field","status","reason","question","suggestions","evidence","actions"],
        "properties": {
            "field": {"type":"string"},
            "status":{"type":"string","enum":["ask","confirm","ok","error"]},
            "reason":{"type":"string"},
            "question":{"type":"string"},
            "suggestions":{
                "type":"array",
                "items":{
                    "type":"object",
                    "required":["value_raw","value_norm","confidence"],
                    "properties":{
                        "value_raw":{"type":"string"},
                        "value_norm":{"type":"string"},
                        "confidence":{"type":"number","minimum":0,"maximum":1}
                    }
                }
            },
            "evidence":{"type":"array","items":{"type":"string"}},
            "actions":{"type":"array","items":{"type":"string"}}
        }
    }

    sample = {
        "field": field,
        "status": "ask",
        "reason": "missing_or_low_confidence",
        "question": "我從文件中擷取了可能的計畫標題：{{ suggestion_list }}，請選擇或修正為正式名稱。",
        "suggestions": [
            {"value_raw": "國 際 事 務 推 動 運 ⽤ 計 畫", "value_norm": "國際事務推動運用計畫", "confidence": 0.90}
        ],
        "evidence": ["p1: 計畫名稱列"],
        "actions": ["accept","edit","show_evidence","skip"]
    }

    user = f"""
[FIELD_TO_ASK]
{field}

[TEMPLATE_YAML]
{tmpl}

[STATE_JSON]
{json.dumps(state, ensure_ascii=False)}

[PARSED_JSON_CLIP]
{parsed_clip}

[JSON_SCHEMA_HINT]
{json.dumps(json_schema_hint, ensure_ascii=False)}

[RESPONSE_FORMAT]
- 僅回『單行 JSON 物件』；禁止回空物件 {{}}；禁止照抄 sample。
- 若抓不到，也要回『{field}』的詢問卡（suggestions 可為空，但結構必須完整）。
- 若有模糊候選，務必輸出 1~3 筆，confidence 取 0.25~0.6（低信心也要回）。

[SAMPLE_ONLY]
{json.dumps(sample, ensure_ascii=False)}
（上方僅作格式參考；最終回覆『只允許單行 JSON 物件』）
""".strip()

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "system", "content": "務必回單行 JSON；嚴禁回 {}；低信心至少一筆候選。"},
        {"role": "user", "content": f"[USER_UTTERANCE_HINT]\n{(user_utterance or '').strip()}"},
    ]

# --- 後端 fallback ---
def ensure_card_output(obj, field: str):
    """確保 LLM 輸出不是空，並且 evidence 一定是 array"""
    if not obj or obj == {}:
        return {
            "field": field,
            "status": "ask",
            "reason": "no_output_from_llm",
            "question": f"無法擷取 {field}，請手動輸入。",
            "suggestions": [],
            "evidence": [],
            "actions": ["edit","skip"]
        }

    # 🔒 確保 evidence 永遠是 list
    ev = obj.get("evidence", [])
    if isinstance(ev, str):
        obj["evidence"] = [ev] if ev.strip() else []
    elif not isinstance(ev, list):
        obj["evidence"] = []

    # 🔒 確保 suggestions 永遠是 list
    sugg = obj.get("suggestions", [])
    if isinstance(sugg, dict):
        obj["suggestions"] = [sugg]
    elif not isinstance(sugg, list):
        obj["suggestions"] = []

    # 🔒 確保 actions 永遠是 list
    acts = obj.get("actions", [])
    if isinstance(acts, str):
        obj["actions"] = [acts]
    elif not isinstance(acts, list):
        obj["actions"] = []

    return obj
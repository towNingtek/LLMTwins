import json
import re
from pathlib import Path

def _clip_text(s: str, max_chars: int = 8000) -> str:
    s = s or ""
    return s[:max_chars]

def _enhance_field_value_extraction(parsed_text: str) -> str:
    """
    預處理：標記欄位標籤，幫助 AI 找到對應的實際內容
    """
    # 定義常見的欄位標籤模式（這些是標籤，不是內容）
    field_label_patterns = [
        r'^計\s*畫\s*名\s*稱',  # 計畫名稱
        r'^畫\s*名\s*稱',      # 破碎的計畫名稱
        r'^計\s*畫\s*性\s*質',  # 計畫性質
        r'^預\s*算\s*類\s*別',  # 預算類別
        r'^計\s*畫\s*依\s*據',  # 計畫依據
        r'^計\s*畫\s*摘\s*要',  # 計畫摘要
    ]
    
    lines = parsed_text.split('\n')
    enhanced_lines = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            enhanced_lines.append(line)
            continue
        
        # 檢查是否為欄位標籤
        is_field_label = False
        for pattern in field_label_patterns:
            if re.match(pattern, line):
                # 標記為欄位標籤，並嘗試找出後續的實際內容
                enhanced_lines.append(f"[FIELD_LABEL] {line}")
                
                # 嘗試找出同一行或下一行的實際內容
                remaining_content = line[len(re.match(pattern, line).group()):].strip()
                if remaining_content:
                    enhanced_lines.append(f"[FIELD_VALUE] {remaining_content}")
                elif i + 1 < len(lines) and lines[i + 1].strip():
                    # 下一行可能是對應的值
                    next_line = lines[i + 1].strip()
                    enhanced_lines.append(f"[FIELD_VALUE_NEXT] {next_line}")
                
                is_field_label = True
                break
        
        if not is_field_label:
            enhanced_lines.append(line)
    
    return '\n'.join(enhanced_lines)

def _enhance_extraction_rules() -> str:
    """
    增強版的抽取規則
    """
    return """
抽取規則（特別針對 title/計畫名稱）：
1. **重點理解**：「畫 名 稱」、「計 畫 名 稱」等是欄位標籤，不是內容
2. **目標內容**：
   - 尋找 [FIELD_VALUE] 或 [FIELD_VALUE_NEXT] 標記的內容
   - 這些是欄位標籤後面對應的實際計畫名稱
   - 如「國 際 事 務 推 動 運 ⽤ 計 畫」等
3. **避開內容**：
   - [FIELD_LABEL] 標記的文字（這些是欄位名稱，不是計畫名稱）
   - 破碎的欄位標籤如「畫 名 稱」「計 畫 性 質」等
4. **候選項評估**：
   - 標記為 [FIELD_VALUE] 的內容 → confidence ≥0.8
   - 未標記但看起來是實質計畫名稱 → confidence 0.5~0.7
   - 明顯是欄位標籤 → 不輸出
5. **文字處理**：OCR 造成的空白要合併，如「國 際 事 務」→「國際事務」
"""

def build_card_messages(sess_base, session_id: str, field: str, user_utterance: str = ""):
    sdir = Path(sess_base) / session_id

    tmpl = (sdir / "config" / "effective_conversation_template.yaml").read_text(encoding="utf-8")
    state = json.loads((sdir / "state" / "conversation_state.json").read_text(encoding="utf-8"))
    parsed_blob = (sdir / "artifacts" / "parsed.json").read_text(encoding="utf-8")
    
    # 🆕 預處理：識別欄位標籤和對應內容
    enhanced_parsed = _enhance_field_value_extraction(parsed_blob)
    parsed_clip = _clip_text(enhanced_parsed, 8000)

    # --- 強化版 system ---
    system = (
        "你是政府CMS導引員。"
        "⚠️ 務必回『單行 JSON 物件』；嚴禁回空物件 {}；嚴禁照抄 sample。\n"
        "若有低信心候選，也必須至少輸出一筆，confidence=0.25 起跳。\n"
        "根據 template/state/parsed，只為『指定欄位』產生『一張卡片』。\n"
        "必填鍵：field,status,reason,question,suggestions,evidence,actions。\n"
        "suggestions 每一項必含：value_raw, value_norm, confidence(0~1)。\n"
        "value_norm 需去除 OCR 破碎空白，全形/半形統一，保留原文於 value_raw。\n"
        "evidence 放簡短定位（如 'p1: 計畫名稱列'）。\n"
        "actions 至少包含 accept, edit, show_evidence, skip。\n"
        "若確實抓不到，也要回『該欄位名』的詢問卡（suggestions 可為空陣列）。\n"
        f"{_enhance_extraction_rules()}\n"
        "信心政策：\n"
        "  - [FIELD_VALUE] 標記的內容 → confidence ≥0.8。\n"
        "  - 實質計畫名稱但未標記 → confidence 0.4~0.7。\n"
        "  - 明顯是欄位標籤（如「畫名稱」）→ 不輸出。\n"
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
            {"value_raw": "國 際 事 務 推 動 運 ⽤ 計 畫", "value_norm": "國際事務推動運用計畫", "confidence": 0.85}
        ],
        "evidence": ["p1: 計畫名稱欄位內容"],
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

[EXTRACTION_NOTES]
- 文件已預處理，[FIELD_LABEL] 為欄位標籤，[FIELD_VALUE] 為對應內容
- 請優先抽取 [FIELD_VALUE] 標記的實際內容，避開欄位標籤
- 注意：「畫名稱」是欄位標籤，「國際事務推動運用計畫」才是真正內容

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
        {"role": "system", "content": "務必回單行 JSON；嚴禁回 {}；優先 [FIELD_VALUE] 標記的內容，避開欄位標籤。"},
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
# app/services/field_prompts.py
def prompt_name(plain: str) -> tuple[str, str]:
    system = "你是一名嚴格的後端小幫手，務必只回單行 JSON。"
    user = f"""從下列文件純文字中抓出「計畫名稱」的最合理候選，若沒有就依照文件，自己創造一個。
僅以 JSON 回覆：{{"name": "<不超過20字>"}}
文件：
{plain}
"""
    return system, user

def prompt_philosophy(plain: str) -> tuple[str, str]:
    system = "你是一名嚴格的後端小幫手，務必只回單行 JSON。"
    user = f"""用 120~180 字摘要此計畫的核心理念/目的，避免表格/清單/引號/JSON片段。
僅以 JSON 回覆：{{"philosophy": "<120~180字>"}}
文件：
{plain}
"""
    return system, user

def prompt_sdg(plain_text: str):
    system = (
        "你是政府專案後端助理。務必只回『單行 JSON』，不加說明/碼框。"
        "輸出欄位：list_sdg（27位0/1逗號字串）與 weight_description（物件，僅含為1的索引鍵）。"
        "weight_description 的每個值都要是 <p>…</p> 簡短HTML段落。"
        "嚴格規則：1) list_sdg 恰為27個0/1；2) 不能全部為0；"
        "3) 若某位元為1，weight_description 必須含對應數字鍵；4) 僅輸出單行JSON。"
    )
    user = (
        "以下是從計畫文件擷取的純文字，請判斷與聯合國SDGs對應並輸出JSON："
        '{"list_sdg":"b1,b2,...,b27","weight_description":{"8":"<p>...</p>","11":"<p>...</p>"}}'
        "。若資訊不足，保守少量打1，但嚴禁全0。\n\n【文件純文字（截斷）】\n"
        + (plain_text or "")
    )
    return system, user

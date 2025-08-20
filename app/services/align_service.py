from pathlib import Path
from datetime import datetime
import json
from typing import Tuple

MAX_CHARS = 8000  # 避免把整份 parsed.json 都塞進去

def _clip_text(s: str, max_chars: int = MAX_CHARS) -> str:
    s = s or ""
    return s[:max_chars]

def load_parsed_clip(sess_base: str, session_id: str, max_chars: int = MAX_CHARS) -> Tuple[str, dict]:
    """讀取 artifacts/parsed.json，回傳 (clip_text, parsed_obj)"""
    p = Path(sess_base) / session_id / "artifacts" / "parsed.json"
    raw = p.read_text(encoding="utf-8")
    return _clip_text(raw, max_chars), json.loads(raw)

def build_upload_prompt(parsed_clip: str,
                        fixed_email: str = "forus999@gmail.com",
                        current_year: int = None) -> str:
    from datetime import datetime
    year = current_year or datetime.now().year
    start_fallback = f"{year}-01-01"
    end_fallback   = f"{year}-12-31"

    return f"""
你是後端助理。根據 parsed.json 產生 `POST /projects/upload` 的參數。
只回「單行 JSON 物件」，不要多餘文字或 Markdown。**嚴格滿足以下硬性規則**：

【硬性規則（不得違反）】
- email 一律為 "{fixed_email}"（不可改）
- project_start_date / project_due_date：
  - 能判斷年度（如「114 年度」= 2025）→ 用該年度 01-01 / 12-31
  - 抓不到 → {start_fallback} / {end_fallback}
- **name 不得為空**：修復 OCR 破碎（例：計 畫→計畫、國 際→國際），在「名稱／計畫名稱／名 稱／計畫書」附近取最完整一行
- **philosophy 不得為空**：由「計畫目的/問題評析」+「執行內容/工作項目」濃縮 80–200 字中文摘要
- budget：整數（單位：元）。若見「(新台幣：千元) N」→ 乘 1000；若有「合計 X,XXX,XXX」以該元值為主；全無法判斷 → 0
- org、hoster_email：文件未明確 → null（不要臆測）
- **list_sdg 一定是 27 位**（逗號分隔 0/1），且**至少 4–8 個為 1，不可全為 0**
  - 位置：1~17=SDG1..17；18=人，19=文，20=地，21=產，22=景；23=德，24=智，25=體，26=群，27=美
  - 關聯指引（關鍵詞→優先設 1）：
    - 17 夥伴關係：國際/兩岸/姐妹市/交流/合作/城市外交
    - 11 城市與社區：城市/觀光/旅遊/燈會/城市韌性
    - 8 就業與經濟成長：產業/經濟/就業/服務業/觀光產值
    - 21 產：產業/農特產品/行銷/招商/產業鏈
    - 22 景：觀光/景點/活動/展演/旅遊
    - 19 文：文化/展演/藝文/在地文化/燈會
    - 24 智：政策研擬/規劃/培力/知識
    - 26 群：社群/協作/公私協力/國際團體/參與
    - 27 美：美學/城市意象/景觀/展演美感
- **weight_description 必須覆蓋所有 list_sdg=1 的索引**（字串鍵），每個值是一段 1–3 句的 **HTML `<p>…</p>`**，說明為何該權重被選中（可引用國際交流、觀光、城市外交、農特產品、燈會等情境）
- is_budget_revealed：budget>0 → true，否則 false

【輸出格式（單行 JSON；鍵順序如下）】
{{
  "email": "{fixed_email}",
  "name": "<string>",
  "project_start_date": "<YYYY-MM-DD>",
  "project_due_date": "<YYYY-MM-DD>",
  "philosophy": "<string>",
  "budget": <number>,
  "org": <null or string>,
  "hoster_email": <null or string>,
  "list_sdg": "<27 comma-separated 0/1>",
  "weight_description": <object>,   // 鍵為為1的索引；值為 <p>…</p>
  "is_budget_revealed": <true or false>
}}

【parsed.json（截斷）】
{parsed_clip}
""".strip()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompts.py
----------
集中管理各任務的 system / user 提示詞模板。
"""
from typing import Tuple, List

def plan_name_prompts() -> Tuple[str, str]:
    system = (
        "你是一個嚴格的資訊抽取器。"
        "任務：只從提供的文件文字中抽取「計畫名稱」（不是文件標題）。"
        "如果同時出現文件標題與計畫名稱，只能回計畫名稱欄位的值。"
        "輸出規則：只輸出一行純文字，不加引號、不加解釋；若找不到，回覆「找不到」。"
    )
    user = "請從上面的《文件內容》抽取「計畫名稱」。"
    return system, user

def summarize_prompts(language: str = "繁體中文") -> Tuple[str, str]:
    system = (
        f"你是專業文件整理助理，請用{language}撰寫，語氣精準流暢。"
        "任務：針對《文件內容》寫出一段完整的文章型摘要，"
        "保持段落連貫，避免條列式。"
    )
    user = (
        "請撰寫一篇 3–5 段的文章型摘要，必須包含以下內容：\n"
        "1. 計畫主要目的與背景\n"
        "2. 重點內容與執行方式\n"
        "3. 預期效應、預期影響或預期效益（若文件中有此段落，請完整納入）"
    )
    return system, user

def summarize_points_prompts(language: str = "繁體中文") -> Tuple[str, str]:
    system = (
        f"你是專業文件整理助理，請用{language}撰寫，語氣精準。"
        "任務：針對《文件內容》寫出扼要的條列式摘要，"
        "每點保留關鍵名詞與數據。"
    )
    user = "請以 5-8 點條列方式摘要《文件內容》的重點。"
    return system, user

def outline_prompts(language: str = "繁體中文") -> Tuple[str, str]:
    system = (
        f"你是專業文件整理助理，請用{language}撰寫，條理清晰。"
        "任務：將《文件內容》整理成結構化大綱（層級式標題與子彙點）。"
    )
    user = "請輸出層級式大綱（H1/H2/H3 或 1./1.1/1.1.1 標記）。"
    return system, user

def qa_prompts(question: str, language: str = "繁體中文") -> Tuple[str, str]:
    system = (
        f"你是謹慎的文件問答助手，請用{language}回答。"
        "只根據提供的內容作答；若無足夠資訊，請明確說明不確定。"
    )
    user = f"《問題》{question}\n請僅根據《文件內容》回答。"
    return system, user

# ---- SDGs（簡式） ----
def sdgs_prompts(language: str = "繁體中文") -> Tuple[str, str]:
    system = (
        f"你是 SDGs 對應專家。請用{language}撰寫。"
        "任務：根據《文件內容》，挑選最相關的 3–5 個聯合國永續發展目標（SDGs）。"
        "【輸出規格（非常重要）】只輸出『純 JSON 陣列』，長度必須為 3、4 或 5；"
        "陣列中每個元素是『僅一個鍵值』的物件，鍵為 '1'..'17' 的字串，值為一句簡潔說明。"
        "【選擇規則】必須緊密對應文件中的具體作法或名詞；除非文本明確提及，禁止選 1/2。"
        "不得輸出任何解釋、註解或 Markdown。"
    )
    user = "請僅輸出 JSON 陣列，長度 3–5；元素為 {\"<1-17>\": \"一句說明\"}。"
    return system, user

# ---- Budget（簡化版，只抽 total） ----
def budget_prompts(language: str = "繁體中文") -> Tuple[str, str]:
    """
    抽取總預算，輸出固定 JSON 物件：
    {
      "total": <int|null>
    }
    * 若文本以「千元/萬元/億」呈現，請自行換算為「元」後輸出整數。
    * 僅能根據文件文字，不可杜撰；若找不到則回傳 null。
    """
    system = (
        f"你是預算抽取助手，請用{language}回覆。"
        "任務：從《文件內容》抽取『總預算金額』並輸出 JSON。"
        "只允許一個欄位：total（阿拉伯數字整數，單位元）。"
        "不得輸出多餘解釋或 Markdown。"
    )
    user = (
        "請只回傳一個 JSON 物件：\n"
        "{ \"total\": 數字 }\n"
        "數字用阿拉伯數字整數表示，不要附加單位、逗號或其他欄位。"
    )
    return system, user

# ---- Bundle ----
def bundle_prompts(task_list: List[str], language: str = "繁體中文") -> Tuple[str, str]:
    """
    一次輸出多任務（純 JSON 物件）。支援鍵：
      plan_name / summarize / summarize_points / outline / qa / sdgs / budget
    規格：
      - plan_name: 只回計畫名稱（不是文件標題）
      - summarize: 文章型摘要
      - sdgs: 長度 3–5 的陣列，每元素僅一個鍵 '1'..'17'；禁止選 1/2（除非文本明確）
      - budget: 依 budget_prompts 規格輸出 { "total": <int|null> }
    """
    want = ", ".join(task_list)
    system = (
        f"你是文件理解與資訊抽取助手。請用{language}輸出。"
        "任務：根據《文件內容》同時完成多個子任務，並以『單一 JSON 物件』回傳。"
        "不要輸出任何解釋或 Markdown，只輸出純 JSON。"
        "規格補充："
        "  • plan_name：只回計畫名稱（不是文件標題），務必在 20 字數以內。；"
        "  • summarize：文章型摘要，需包含計畫目的、重點內容，以及預期效應/影響/效益；"
         "• sdgs：請僅輸出JSON 陣列，長度 3–5；元素為 {\"<1-17>\": \"一句說明\"}。"
        "  • budget：輸出 { \"total\": 整數 }，單位為元，不得包含其他欄位。"
    )
    user = f"請僅輸出包含這些鍵的 JSON 物件：{want}。"
    return system, user
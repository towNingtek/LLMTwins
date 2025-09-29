#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompts.py
----------
集中管理各任務的 system / user 提示詞模板。
"""

from typing import Tuple

def plan_name_prompts() -> Tuple[str, str]:
    system = (
        "你是一個嚴格的資訊抽取器。"
        "任務：只從提供的文件文字中抽取「計畫名稱」（不是文件標題）。"
        "如果同時出現文件標題與計畫名稱，只能回計畫名稱欄位的值。"
        "輸出規則：只輸出一行純文字，不加引號、不加解釋；若找不到，回覆「找不到」。"
    )
    return system, "請從上面的《文件內容》抽取「計畫名稱」。"

def summarize_prompts(language: str = "繁體中文") -> Tuple[str, str]:
    system = (
        f"你是專業文件整理助理，請用{language}撰寫，語氣精準流暢。"
        "任務：針對《文件內容》寫出一段完整的文章型摘要，"
        "保持段落連貫，避免條列式。"
    )
    user = "請撰寫一篇 3–5 段的文章型摘要，涵蓋主要目的、重點內容與可能影響。"
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
        f"你是謹慎的文件問答助手，請用{language}回答。若無足夠資訊，請明确說明不確定。"
    )
    user = f"《問題》{question}\n請僅根據《文件內容》回答。"
    return system, user

def sdgs_prompts(language: str = "繁體中文") -> Tuple[str, str]:
    """
    產出 3–5 個 SDGs 對應，純 JSON 陣列，元素為 { "<1-17>": "描述" }。
    """
    system = (
        f"你是 SDGs 對應專家。請用{language}撰寫。"
        "任務：根據《文件內容》，挑選最相關的 3–5 個聯合國永續發展目標（SDGs），"
        "並以『純 JSON』輸出。"
        "格式必須是 JSON 陣列（array），陣列中每個元素是一個物件，且只包含一個鍵："
        "鍵為 '1'..'17' 之一（字串），值為一句簡潔的{language}說明，描述文件如何對應該目標。"
        "不得輸出任何解釋、註解或 Markdown。只輸出 JSON。"
        "SDGs 參考（僅供編碼）："
        "1 無貧窮；2 零飢餓；3 健康與福祉；4 優質教育；5 性別平等；6 淨水與衛生；"
        "7 可負擔乾淨能源；8 合適的工作與經濟成長；9 工業創新與基礎建設；10 減少不平等；"
        "11 永續城鄉；12 責任消費與生產；13 氣候行動；14 水下生命；15 陸域生態；"
        "16 和平正義與健全制度；17 夥伴關係。"
    )
    user = (
        "請僅輸出 JSON 陣列，包含 3–5 個元素，每個元素為："
        "{\"<1-17>\": \"（一句{language}描述）\"}。"
    )
    return system, user


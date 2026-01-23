#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx_ingest.py
--------------
解析南投縣計畫數位管理系統的固定格式 DOCX 範本。

範本欄位：
- 單位名稱
- 計畫名稱
- 計畫摘要
- 計畫內容
- 預期效益
- SROI (忽略)
- 計畫期間
- 經費概數
- 實施區域
"""
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from docx import Document


# 範本欄位定義（順序很重要，用於偵測缺失欄位）
TEMPLATE_FIELDS = [
    "單位名稱",
    "計畫名稱",
    "計畫摘要",
    "計畫內容",
    "預期效益",
    "SROI",
    "計畫期間",
    "經費概數",
    "實施區域",
]

# 必填欄位
REQUIRED_FIELDS = ["單位名稱", "計畫名稱", "計畫摘要", "計畫期間", "經費概數"]


def extract_fields_from_docx(docx_path: Path) -> Tuple[Dict[str, str], List[str]]:
    """
    從 DOCX 提取欄位。

    Returns:
        (fields_dict, errors_list)
        - fields_dict: {"單位名稱": "計畫處", "計畫名稱": "...", ...}
        - errors_list: ["找不到「計畫名稱」欄位", ...]
    """
    doc = Document(docx_path)

    # 方法 1: 嘗試從表格提取
    fields = _extract_from_tables(doc)

    # 方法 2: 如果表格沒資料，嘗試從段落提取
    if not fields:
        fields = _extract_from_paragraphs(doc)

    # 驗證必填欄位
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in fields or not fields[field].strip():
            errors.append(f"找不到「{field}」欄位或欄位為空")

    return fields, errors


def _extract_from_tables(doc: Document) -> Dict[str, str]:
    """從表格中提取欄位（範本通常是表格格式）"""
    fields = {}

    for table in doc.tables:
        for row in table.rows:
            cells = row.cells
            if len(cells) >= 2:
                # 第一欄是欄位名稱，第二欄是值
                field_name = cells[0].text.strip()
                field_value = cells[1].text.strip()

                # 檢查是否為已知欄位
                for template_field in TEMPLATE_FIELDS:
                    if template_field in field_name:
                        fields[template_field] = field_value
                        break

    return fields


def _extract_from_paragraphs(doc: Document) -> Dict[str, str]:
    """從段落中提取欄位（備用方法）"""
    fields = {}
    full_text = "\n".join([p.text for p in doc.paragraphs])

    for field in TEMPLATE_FIELDS:
        # 嘗試匹配「欄位名稱：值」或「欄位名稱\n值」
        pattern = rf"{field}[：:\s]+(.+?)(?=(?:{'|'.join(TEMPLATE_FIELDS)})|$)"
        match = re.search(pattern, full_text, re.DOTALL)
        if match:
            fields[field] = match.group(1).strip()

    return fields


def parse_period(period_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    解析計畫期間字串。

    輸入格式：
    - "114.1-114.12"
    - "114年1月-114年12月"
    - "2025-01-01 至 2025-12-31"

    Returns:
        (start_date, end_date) 格式為 "YYYY-MM-DD"
    """
    if not period_str:
        return None, None

    # 嘗試匹配民國年格式：114.1-114.12
    match = re.match(r"(\d{2,3})\.(\d{1,2})\s*[-~至]\s*(\d{2,3})\.(\d{1,2})", period_str)
    if match:
        start_year = int(match.group(1)) + 1911
        start_month = int(match.group(2))
        end_year = int(match.group(3)) + 1911
        end_month = int(match.group(4))
        return (
            f"{start_year}-{start_month:02d}-01",
            f"{end_year}-{end_month:02d}-28"  # 簡化處理，用 28 日
        )

    # 嘗試匹配西元年格式：2025-01-01
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})\s*[-~至]\s*(\d{4})-(\d{2})-(\d{2})", period_str)
    if match:
        return (
            f"{match.group(1)}-{match.group(2)}-{match.group(3)}",
            f"{match.group(4)}-{match.group(5)}-{match.group(6)}"
        )

    return None, None


def parse_budget(budget_str: str) -> Optional[int]:
    """
    解析經費概數字串。

    輸入格式：
    - "1909000"
    - "1,909,000"
    - "190.9萬"
    - "190萬9千"
    """
    if not budget_str:
        return None

    # 移除逗號和空白
    budget_str = budget_str.replace(",", "").replace(" ", "").strip()

    # 純數字
    if budget_str.isdigit():
        return int(budget_str)

    # 萬元
    match = re.match(r"([\d.]+)\s*萬", budget_str)
    if match:
        return int(float(match.group(1)) * 10000)

    # 千元
    match = re.match(r"([\d.]+)\s*千", budget_str)
    if match:
        return int(float(match.group(1)) * 1000)

    # 嘗試提取數字
    numbers = re.findall(r"\d+", budget_str)
    if numbers:
        return int("".join(numbers))

    return None


def build_philosophy(fields: Dict[str, str]) -> str:
    """
    將多個欄位合併成結構化的 philosophy 文字。
    """
    sections = []

    if fields.get("計畫摘要"):
        sections.append(f"【計畫摘要】\n{fields['計畫摘要']}")

    if fields.get("計畫內容"):
        sections.append(f"【計畫內容】\n{fields['計畫內容']}")

    if fields.get("預期效益"):
        sections.append(f"【預期效益】\n{fields['預期效益']}")

    if fields.get("實施區域"):
        sections.append(f"【實施區域】\n{fields['實施區域']}")

    return "\n\n".join(sections)


def docx_to_bundle(docx_path: Path) -> Tuple[Dict[str, Any], List[str]]:
    """
    將 DOCX 轉換為 bundle 格式（與 PDF LLM 抽取的格式相容）。

    Returns:
        (bundle, errors)
        - bundle: {"plan_name": "...", "summarize": "...", "budget": {"total": 123}, ...}
        - errors: ["錯誤訊息", ...]
    """
    fields, errors = extract_fields_from_docx(docx_path)

    if errors:
        return {}, errors

    # 解析期間
    start_date, end_date = parse_period(fields.get("計畫期間", ""))

    # 解析預算
    budget_total = parse_budget(fields.get("經費概數", ""))

    bundle = {
        "plan_name": fields.get("計畫名稱", ""),
        "summarize": build_philosophy(fields),
        "budget": {"total": budget_total},
        "sdgs": [],  # DOCX 版本不含 SDGs，由 LLM 後續生成
        # 額外欄位（給 bundle_to_payload 用）
        "_docx_fields": {
            "project_b": fields.get("單位名稱", ""),
            "start_date": start_date,
            "end_date": end_date,
        }
    }

    return bundle, []


def extract_full_text_from_docx(docx_path: Path) -> str:
    """從 DOCX 提取所有文字（用於非範本 DOCX 的 LLM 處理）"""
    doc = Document(docx_path)
    texts = []

    # 段落文字
    for para in doc.paragraphs:
        if para.text.strip():
            texts.append(para.text.strip())

    # 表格文字
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                texts.append(row_text)

    return "\n".join(texts)


def ingest_docx_and_write_parsed(sess_base: str, session_id: str) -> Dict[str, Any]:
    """
    從 session 目錄讀取 DOCX 並寫入 parsed.json。

    與 pdf_ingest.ingest_first_pdf_and_write_parsed 相同的介面。

    行為：
    - 若符合範本格式：使用範本解析，產生 docx_bundle
    - 若不符合範本：提取全文，走 LLM 流程（比照 PDF）
    """
    session_dir = Path(sess_base) / session_id
    raw_dir = session_dir / "raw"
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 找到第一個 DOCX 檔案
    docx_files = list(raw_dir.glob("*.docx"))
    if not docx_files:
        return {"ok": False, "error": "找不到 DOCX 檔案"}

    docx_path = docx_files[0]

    # 嘗試提取範本欄位
    fields, errors = extract_fields_from_docx(docx_path)

    # 若不符合範本格式，改用全文提取（比照 PDF 流程）
    if errors:
        full_text = extract_full_text_from_docx(docx_path)

        parsed = {
            "doc": {
                "sid": session_id,
                "filename": docx_path.name,
                "pages": 1,
                "source": "docx_freeform",  # 標記為非範本 DOCX
            },
            "pages": [{"page": 1, "text": full_text}],
            "chunks": [{"id": 0, "page": 1, "start_char": 0, "end_char": len(full_text), "text": full_text}],
            # 不含 docx_bundle，會走 LLM 流程
        }

        parsed_path = artifacts_dir / "parsed.json"
        with open(parsed_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)

        return {
            "ok": True,
            "filename": docx_path.name,
            "mode": "llm_fallback",
            "reason": "DOCX 格式不符範本，將使用 LLM 智能抽取",
        }

    # 建立 bundle（範本格式）
    bundle, bundle_errors = docx_to_bundle(docx_path)

    if bundle_errors:
        # bundle 轉換失敗也走 LLM 流程
        full_text = extract_full_text_from_docx(docx_path)

        parsed = {
            "doc": {
                "sid": session_id,
                "filename": docx_path.name,
                "pages": 1,
                "source": "docx_freeform",
            },
            "pages": [{"page": 1, "text": full_text}],
            "chunks": [{"id": 0, "page": 1, "start_char": 0, "end_char": len(full_text), "text": full_text}],
        }

        parsed_path = artifacts_dir / "parsed.json"
        with open(parsed_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)

        return {
            "ok": True,
            "filename": docx_path.name,
            "mode": "llm_fallback",
            "reason": "DOCX 轉換失敗，將使用 LLM 智能抽取",
        }

    # 建立與 PDF parsed.json 相容的格式（範本模式）
    full_text = build_philosophy(fields)

    parsed = {
        "doc": {
            "sid": session_id,
            "filename": docx_path.name,
            "pages": 1,
            "source": "docx_template",
        },
        "pages": [{"page": 1, "text": full_text}],
        "chunks": [{"id": 0, "page": 1, "start_char": 0, "end_char": len(full_text), "text": full_text}],
        # DOCX 專屬：預先抽取的欄位
        "docx_bundle": bundle,
        "docx_fields": fields,
    }

    # 寫入 parsed.json
    parsed_path = artifacts_dir / "parsed.json"
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "filename": docx_path.name,
        "mode": "template",
        "fields_found": list(fields.keys()),
        "bundle": bundle,
    }

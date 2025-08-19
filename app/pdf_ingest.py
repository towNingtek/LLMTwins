# app/pdf_ingest.py
# -*- coding: utf-8 -*-
"""
PDF ingestion with OCR fallback (ocrmypdf) + pdfminer extraction + safe chunking.
產出 parsed.json 的 payload，並回傳執行情況與品質標記（ocr_used/ocr_quality）。
"""

from __future__ import annotations
import os, re, json, glob, subprocess
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# 先自載 .env，避免 import 順序問題
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

import yaml
from pdfminer.high_level import extract_text

# ---------------------- 動態抓設定 ----------------------
def _cfg() -> Dict[str, Any]:
    return {
        "OCR_ENABLED": os.getenv("OCR_ENABLED", "true").lower() in ("1", "true", "yes"),
        "OCR_LANG": os.getenv("OCR_LANG", "chi_tra+eng"),
        "OCR_TEXTLEN_THRESHOLD": int(os.getenv("OCR_TEXTLEN_THRESHOLD", "30")),
        "OCR_TIMEOUT_SEC": int(os.getenv("OCR_TIMEOUT_SEC", "600")),
        "SAFE_CHUNK_SIZE": int(os.getenv("INGEST_CHUNK_SIZE", "1200")),
        "SAFE_OVERLAP": int(os.getenv("INGEST_CHUNK_OVERLAP", "120")),
    }

# ---------------------- Data structures ----------------------
@dataclass
class IngestResult:
    ok: bool
    pages: int
    chunks: int
    filename: str
    ocr_used: bool
    ocr_quality: str  # "ok" | "low" | ""
    error: Optional[str] = None
    parsed_json_path: Optional[str] = None

# ---------------------- Utilities ----------------------
def _clean_text(s: str) -> str:
    s = s.replace("\x00", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\r\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _paragraph_split(s: str) -> List[str]:
    parts = [p.strip() for p in s.split("\n\n") if p.strip()]
    return parts if len(parts) > 2 else [s]

def _make_chunks(text: str, page: int, base_id: str, *, chunk_size: int, overlap: int):
    chunks = []
    if not text.strip():
        return chunks
    paras = _paragraph_split(text)
    buf = ""
    start_idx = 0
    cid = 1
    for para in paras:
        add = (buf + ("\n\n" if buf else "") + para).strip()
        if len(add) <= chunk_size:
            buf = add
            continue
        if buf:
            end_idx = start_idx + len(buf)
            chunks.append({"id": f"{base_id}c{cid}", "page": page,
                           "start_char": start_idx, "end_char": end_idx, "text": buf})
            cid += 1
            keep = buf[-overlap:] if len(buf) > overlap else buf
            buf = (keep + "\n\n" + para).strip()
            start_idx = end_idx - len(keep)
        else:
            long = para
            pos = 0
            while pos < len(long):
                piece = long[pos:pos+chunk_size]
                end_idx = start_idx + len(piece)
                chunks.append({"id": f"{base_id}c{cid}", "page": page,
                               "start_char": start_idx, "end_char": end_idx, "text": piece})
                cid += 1
                pos += chunk_size - overlap
                start_idx = end_idx - overlap
            buf = ""
            start_idx += overlap
    if buf:
        end_idx = start_idx + len(buf)
        chunks.append({"id": f"{base_id}c{cid}", "page": page,
                       "start_char": start_idx, "end_char": end_idx, "text": buf})
    return chunks

def _extract_pages_text(pdf_path: str) -> List[str]:
    full = extract_text(pdf_path) or ""
    pages = [p for p in full.split("\x0c") if p.strip()] or [full]
    return [_clean_text(p) for p in pages]

def _ocr_pdf_to_searchable(src_pdf: Path, dst_pdf: Path, *, lang: str, timeout_sec: int) -> Dict[str, Any]:
    cmd = [
        "ocrmypdf",
        "--skip-text",
        "--optimize", "0",
        "--deskew",
        "--rotate-pages",
        "--language", lang,
        str(src_pdf),
        str(dst_pdf),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        return {"ok": r.returncode == 0, "code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    except FileNotFoundError:
        return {"ok": False, "code": -1, "error": "ocrmypdf not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -2, "error": f"OCR timeout > {timeout_sec}s"}
    except Exception as e:
        return {"ok": False, "code": -3, "error": repr(e)}

def _pages_quality_flag(pages: List[str]) -> str:
    if not pages:
        return "low"
    total = sum(len(p) for p in pages)
    if total < 10:
        return "low"
    raw = "\n".join(pages)
    if not raw:
        return "low"
    keep = re.findall(r"[A-Za-z0-9\u4e00-\u9fff\s]", raw)
    ratio_keep = (len(keep) / len(raw)) if len(raw) else 0
    return "ok" if ratio_keep >= 0.6 else "low"

def _pending_fields_from_catalog(base_dir: Path, model: str = "project") -> List[str]:
    path = base_dir / f"configs/field_catalogs/{model}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    fields = (cfg.get("fields") or {}).items()
    return [name for name, spec in fields if (spec or {}).get("required") is True]

# ---------------------- Public API ----------------------
def ingest_first_pdf_and_write_parsed(
    session_id: str,
    sess_base: Path,
    base_dir: Path,
    model: str = "project",
) -> IngestResult:
    """
    從 sessions/<sid>/raw/*.pdf 取第一個，嘗試抽文字。
    若抽不到且 OCR_ENABLED，使用 ocrmypdf 產生 artifacts/ocr_searchable.pdf 再抽一次。
    產出 artifacts/parsed.json，並回傳 IngestResult（含 ocr 標記與品質）。
    """
    cfg = _cfg()

    sdir = sess_base / session_id
    raw_dir = sdir / "raw"
    art_dir = sdir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(glob.glob(str(raw_dir / "*.pdf")))
    if not pdfs:
        return IngestResult(False, 0, 0, "", False, "", error="no pdf in raw/")

    pdf_path = Path(pdfs[0])  # 可換成最新檔：Path(max(pdfs, key=os.path.getmtime))
    pages1 = _extract_pages_text(str(pdf_path))
    total_len1 = sum(len(p) for p in pages1)

    ocr_used = False
    pages_final = pages1

    if total_len1 < cfg["OCR_TEXTLEN_THRESHOLD"] and cfg["OCR_ENABLED"]:
        ocr_pdf = art_dir / "ocr_searchable.pdf"
        ocr_res = _ocr_pdf_to_searchable(
            pdf_path, ocr_pdf,
            lang=cfg["OCR_LANG"],
            timeout_sec=cfg["OCR_TIMEOUT_SEC"]
        )
        if ocr_res.get("ok"):
            pages2 = _extract_pages_text(str(ocr_pdf))
            if sum(len(p) for p in pages2) > total_len1:
                pages_final = pages2
                ocr_used = True
        # 失敗就沿用原結果

    chunks = []
    for i, t in enumerate(pages_final, start=1):
        chunks.extend(_make_chunks(
            t, i, base_id=f"p{i}",
            chunk_size=cfg["SAFE_CHUNK_SIZE"],
            overlap=cfg["SAFE_OVERLAP"]
        ))

    ocr_quality = _pages_quality_flag(pages_final) if ocr_used else ""

    payload = {
        "doc": {
            "sid": session_id,
            "filename": pdf_path.name,
            "pages": len(pages_final),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "ocr_used": ocr_used,
            "ocr_quality": ocr_quality,
        },
        "pages": [{"page": i, "text": t} for i, t in enumerate(pages_final, start=1)],
        "chunks": chunks,
    }

    out_path = art_dir / "parsed.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return IngestResult(
        ok=True,
        pages=len(pages_final),
        chunks=len(chunks),
        filename=pdf_path.name,
        ocr_used=ocr_used,
        ocr_quality=ocr_quality,
        parsed_json_path=str(out_path),
    )

def list_required_fields(base_dir: Path, model: str = "project") -> List[str]:
    return _pending_fields_from_catalog(base_dir, model)
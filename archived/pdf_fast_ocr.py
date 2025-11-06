#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_fast_ocr.py (parallel)
--------------------------
Fast OCR for PDFs using Tesseract via pytesseract (PyMuPDF renders pages).

Public API:
  - resolve_tessdata_dir() -> str | None
  - pdf_to_text(pdf_path: str, lang: str = "chi_tra", dpi: int = 200, jobs: int = 1) -> str
  - pdf_to_text_file(pdf_path: str, out_path: str, lang: str = "chi_tra", dpi: int = 200,
                     per_page: bool = False, encoding: str = "utf-8", jobs: int = 1) -> str | list[str]
"""
import os
import io
from typing import Optional, List, Union, Tuple
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from concurrent.futures import ProcessPoolExecutor, as_completed

__all__ = ["resolve_tessdata_dir", "pdf_to_text", "pdf_to_text_file"]

def _file_exists(path: str) -> bool:
    try:
        return os.path.isfile(path)
    except Exception:
        return False

def resolve_tessdata_dir() -> Optional[str]:
    cand = os.environ.get("TESSDATA_DIR")
    if cand and _file_exists(os.path.join(cand, "eng.traineddata")):
        return cand
    pfx = os.environ.get("TESSDATA_PREFIX")
    if pfx:
        if _file_exists(os.path.join(pfx, "eng.traineddata")):
            return pfx
        nested = os.path.join(pfx, "tessdata")
        if _file_exists(os.path.join(nested, "eng.traineddata")):
            return nested
    hb = "/opt/homebrew/share/tessdata"
    if _file_exists(os.path.join(hb, "eng.traineddata")):
        return hb
    intel = "/usr/local/share/tessdata"
    if _file_exists(os.path.join(intel, "eng.traineddata")):
        return intel
    return None

def _extra_cfg() -> str:
    tdir = resolve_tessdata_dir()
    if tdir:
        os.environ["TESSDATA_PREFIX"] = os.path.dirname(tdir)
        return f' --tessdata-dir "{tdir}"'
    return ""

def _render_and_ocr(pdf_path: str, page_index: int, dpi: int, lang: str, extra_cfg: str) -> Tuple[int, str]:
    # 子行程內重開 PDF，避免跨程序物件
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_index)
    # alpha=False 降檔，convert('L') 灰階 → Tesseract 較快
    pix = page.get_pixmap(dpi=int(dpi), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    txt = pytesseract.image_to_string(img, lang=lang, config=f"--psm 6 --oem 1{extra_cfg}")
    return page_index, txt

def _ocr_sequential(pdf_path: str, lang: str, dpi: int, extra: str) -> List[str]:
    doc = fitz.open(pdf_path)
    out = []
    for i in range(len(doc)):
        _, txt = _render_and_ocr(pdf_path, i, dpi, lang, extra)
        out.append(txt)
    return out

def _ocr_parallel(pdf_path: str, lang: str, dpi: int, extra: str, jobs: int) -> List[str]:
    doc = fitz.open(pdf_path)
    n = len(doc)
    results = [None] * n
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = [ex.submit(_render_and_ocr, pdf_path, i, dpi, lang, extra) for i in range(n)]
        for fut in as_completed(futs):
            i, txt = fut.result()
            results[i] = txt
    return results  # 依索引還原原始順序

def pdf_to_text(pdf_path: str, lang: str = "chi_tra", dpi: int = 200, jobs: int = 1) -> str:
    """OCR 全文；jobs>1 時使用多進程平行化。"""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(pdf_path)
    extra = _extra_cfg()
    if jobs and jobs > 1:
        texts = _ocr_parallel(pdf_path, lang=lang, dpi=dpi, extra=extra, jobs=jobs)
    else:
        texts = _ocr_sequential(pdf_path, lang=lang, dpi=dpi, extra=extra)
    return "\n".join(texts)

def pdf_to_text_file(
    pdf_path: str,
    out_path: str,
    lang: str = "chi_tra",
    dpi: int = 200,
    per_page: bool = False,
    encoding: str = "utf-8",
    jobs: int = 1,
) -> Union[str, List[str]]:
    """把 OCR 寫入檔案（單檔或逐頁）。"""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(pdf_path)
    extra = _extra_cfg()
    doc = fitz.open(pdf_path)

    if not per_page:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        if jobs and jobs > 1:
            chunks = _ocr_parallel(pdf_path, lang, dpi, extra, jobs)
        else:
            chunks = _ocr_sequential(pdf_path, lang, dpi, extra)
        with open(out_path, "w", encoding=encoding) as f:
            for p, txt in enumerate(chunks, start=1):
                f.write(txt)
                if p != len(chunks):
                    f.write("\n" + "-" * 80 + f"\n[Page {p} End]\n" + "-" * 80 + "\n")
        return out_path

    # per_page: out_path 當資料夾
    os.makedirs(out_path, exist_ok=True)
    width = max(3, len(str(len(doc))))
    paths: List[str] = []
    if jobs and jobs > 1:
        chunks = _ocr_parallel(pdf_path, lang, dpi, extra, jobs)
        for i, txt in enumerate(chunks):
            fn = os.path.join(out_path, f"page_{i+1:0{width}d}.txt")
            with open(fn, "w", encoding=encoding) as f:
                f.write(txt)
            paths.append(fn)
    else:
        for i in range(len(doc)):
            _, txt = _render_and_ocr(pdf_path, i, dpi, lang, extra)
            fn = os.path.join(out_path, f"page_{i+1:0{width}d}.txt")
            with open(fn, "w", encoding=encoding) as f:
                f.write(txt)
            paths.append(fn)
    return paths


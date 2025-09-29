# app/services/ingest_service.py
from pathlib import Path
from app.session_utils import append_history
from app.logger import logger

def parse_first_pdf_and_write(session_id: str, base_dir: Path, sess_base: Path, state_store, model: str = "project") -> dict:
    # 延遲載入，避免啟動就吃 heavy 依賴
    from app.pdf_ingest import ingest_first_pdf_and_write_parsed, list_required_fields

    # Debug msg
    print(f"[ingest]Hello  parse_first_pdf_and_write: session_id={session_id}, model={model}")

    res = ingest_first_pdf_and_write_parsed(
        session_id=session_id,
        sess_base=sess_base,
        base_dir=base_dir,
        model=model,
    )

    if not res.ok:
        return {"ok": False, "error": res.error or "ingest failed"}

    # required fields
    try:
        pending_fields = list_required_fields(base_dir, model=model)
    except Exception as e:
        pending_fields = []
        logger.error("[state] list_required_fields error:", e)

    # 更新 state
    try:
        state_store.mark_parsed(
            session_id,
            filename=res.filename,
            pages=res.pages,
            pending_fields=pending_fields,
        )
    except Exception as e:
        logger.error("[state] mark_parsed error:", e)

    # 系統訊息
    try:
        ocr_tag = f", ocr_used={res.ocr_used}, ocr_quality={res.ocr_quality or '-'}"
        append_history(
            session_id,
            "system",
            f"[parsed] {res.filename} → artifacts/parsed.json (pages={res.pages}, chunks={res.chunks}{ocr_tag})",
            sess_base,
        )
    except Exception:
        pass

    # Debug msg
    print(f"[ingest]Hello .. parse_first_pdf_and_write: session_id={session_id}")

    return {"ok": True, "pages": res.pages, "chunks": res.chunks, "filename": res.filename}

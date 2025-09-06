# app/routers/sessions.py
from fastapi import UploadFile, File
from fastapi import Query
from pathlib import Path
import time
from fastapi import APIRouter, Request, HTTPException
import uuid
from app.logger import logger

from app.session_utils import (
    session_dir, ensure_dir, append_history,   # append_history 這步用不到，但之後 upload 會用
    init_session_dirs, write_effective_template
)
from app.services.ingest_service import parse_first_pdf_and_write

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

@router.post("")
async def create_session(request: Request):
    # 從 app.state 取得共用資源（避免跨檔案硬依賴）
    sess_base = request.app.state.sess_base
    base_dir  = request.app.state.base_dir
    state_store = request.app.state.state_store

    sid = "sess_" + uuid.uuid4().hex

    # 建目錄 + 生效模板
    init_session_dirs(sid, sess_base)
    init_res = write_effective_template(sid, base_dir, sess_base, model="project")

    # 初始化對話狀態
    try:
        st = state_store.init_session(sid)
    except Exception as e:
        st = {"error": f"state init failed: {e}"}

    return {"session_id": sid, "init": init_res, "state": st}

@router.get("/{session_id}/state")
async def get_session_state(session_id: str, request: Request):
    state_store = request.app.state.state_store
    try:
        st = state_store.get(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"state error: {e}")

    if not st:
        raise HTTPException(status_code=404, detail="state not found")

    return {"ok": True, "state": st}

@router.post("/{session_id}/upload")
async def upload_to_session(session_id: str, request: Request,
                           file: UploadFile = File(...),
                           auto_parse: bool = Query(True, description="是否自動解析 PDF 並更新 state")):
   sess_base = request.app.state.sess_base
   base_dir = request.app.state.base_dir
   state_store = request.app.state.state_store

   d = session_dir(session_id, sess_base)
   raw_dir = d / "raw"
   ensure_dir(raw_dir)

   orig_name = (file.filename or "upload.bin")
   orig_name = Path(orig_name).name
   suffix = Path(orig_name).suffix.lower()

   # 如果是 PDF，先清理舊的 PDF 檔案和解析結果
   if suffix == ".pdf":
       # 清理舊的 PDF 檔案
       for old_pdf in raw_dir.glob("*.pdf"):
           try:
               old_pdf.unlink()
               logger.info(f"Removed old PDF: {old_pdf.name}")
           except Exception as e:
               logger.warning(f"Failed to remove old PDF {old_pdf.name}: {e}")
       
       # 清理舊的解析結果
       artifacts_dir = d / "artifacts"
       if artifacts_dir.exists():
           for old_file in ["parsed.json", "ocr_searchable.pdf"]:
               old_path = artifacts_dir / old_file
               if old_path.exists():
                   try:
                       old_path.unlink()
                       logger.info(f"Removed old artifact: {old_file}")
                   except Exception as e:
                       logger.warning(f"Failed to remove {old_file}: {e}")

   ts = int(time.time() * 1000)
   dest_name = f"{ts}_{uuid.uuid4().hex}{suffix}"
   dest_path = raw_dir / dest_name

   size = 0
   try:
       with dest_path.open("wb") as out:
           while True:
               chunk = await file.read(1024 * 1024)  # 1MB
               if not chunk:
                   break
               size += len(chunk)
               out.write(chunk)
   finally:
       try:
           await file.close()
       except Exception:
           pass

   # 記錄上傳事件
   try:
       append_history(session_id, "system", f"[upload] {orig_name} -> raw/{dest_name} ({size} bytes)", sess_base)
   except Exception:
       pass

   # 可選解析
   parse_result = None
   if suffix == ".pdf" and auto_parse:
       try:
           parse_result = parse_first_pdf_and_write(session_id, base_dir, sess_base, state_store, model="project")
       except Exception as e:
           parse_result = {"ok": False, "error": f"parse failed: {e}"}

   return {
       "ok": True,
       "session_id": session_id,
       "name": orig_name,
       "stored_as": dest_name,
       "size": size,
       "mime": file.content_type,
       "path": str(dest_path.relative_to(sess_base)),
       "parse": parse_result,
   }
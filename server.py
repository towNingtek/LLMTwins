import json
import os
import asyncio
import traceback
import uuid
import time
from pathlib import Path

import aiohttp
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from policy.guard import DenyGuard
from fastapi import UploadFile, File

import yaml
from copy import deepcopy
from app.state_store import ConversationStateStore

from fastapi import Query
import glob

# from app.pdf_ingest import ingest_first_pdf_and_write_parsed, list_required_fields


# ============================================================================
# Configuration & Initialization
# ============================================================================

def ndjson_line(obj: dict) -> bytes:
    """Convert dict to NDJSON line format"""
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

# Environment variables
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://140.127.196.91:8082")
OLLAMA_AUTH = os.getenv("OLLAMA_AUTH")
DENYLIST_PATH = os.getenv("DENYLIST_JSON", "policy/deny.json")
DENY_ENABLED = os.getenv("DENY_ENABLED", "true").lower() in ("1", "true", "yes")

# Session storage base (filesystem for now)
SESS_BASE = Path(os.getenv("SESS_BASE", "sessions"))
SESS_BASE.mkdir(parents=True, exist_ok=True)

# FastAPI app initialization
app = FastAPI()

# CORS configuration
ALLOWED_ORIGINS = [
    "https://eva.4impact.cc",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://nsdgs.4impact.cc",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------------
# Session helpers
# ----------------------------------------------------------------------------

def _deep_merge(a, b):
    """dict 深合併：b 覆蓋 a"""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return deepcopy(b)
    out = deepcopy(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def _init_session_files(session_id: str, model: str = "project") -> dict:
    """
    建立 session 目錄與生效模板：
      sessions/<sid>/{config,state,artifacts}/
      sessions/<sid>/config/effective_conversation_template.yaml
    """
    sdir = _session_dir(session_id)
    _ensure_dir(sdir / "config")
    _ensure_dir(sdir / "state")
    _ensure_dir(sdir / "artifacts")

    base_tpl = BASE_DIR / f"configs/conversation_templates/{model}.yaml"
    eff_path = sdir / "config" / "effective_conversation_template.yaml"
    overrides_path = sdir / "config" / "template_overrides.yaml"

    # 讀 global 模板
    if not base_tpl.exists():
        return {"ok": False, "reason": f"missing global template: {base_tpl}"}
    with base_tpl.open("r", encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f) or {}

    # 合併 overrides（若有）
    if overrides_path.exists():
        with overrides_path.open("r", encoding="utf-8") as f:
            overrides = yaml.safe_load(f) or {}
        eff_cfg = _deep_merge(base_cfg, overrides)
    else:
        eff_cfg = base_cfg

    # 輸出生效版
    with eff_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(eff_cfg, f, allow_unicode=True, sort_keys=False)

    return {"ok": True, "effective": str(eff_path)}

def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def _session_dir(session_id: str) -> Path:
    return SESS_BASE / session_id


def _append_history(session_id: str, role: str, content: str):
    """Append one line NDJSON to chat_history.jsonl"""
    if not content:
        return
    d = _session_dir(session_id)
    _ensure_dir(d)
    fp = d / "chat_history.jsonl"
    rec = {"ts": time.time(), "role": role, "content": content}
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")


# ============================================================================
# Startup Events & Policy Loading
# ============================================================================

@app.on_event("startup")
async def load_policy_on_startup():
    """Load policy guard on startup"""
    app.state.state_store = ConversationStateStore(SESS_BASE)

    try:
        app.state.deny_guard = DenyGuard.load_from_path(DENYLIST_PATH)
        app.state.deny_enabled = DENY_ENABLED
        print(
            f"[policy] loaded {DENYLIST_PATH}:",
            app.state.deny_guard.summary(),
            "enabled=",
            app.state.deny_enabled,
        )
    except Exception as e:
        app.state.deny_guard = None
        app.state.deny_enabled = False
        print(f"[policy] load failed: {e} (policy disabled)")

# ============================================================================
# Health Check & Root Endpoints
# ============================================================================

@app.get("/")
@app.head("/")
async def root_ok():
    """Root endpoint for health check"""
    return Response(status_code=204)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"result": "Healthy Server!"}

# ============================================================================
# Policy Management Endpoints
# ============================================================================

@app.get("/debug/policy")
async def debug_policy():
    """Get current policy configuration"""
    dg = getattr(app.state, "deny_guard", None)
    return {
        "enabled": getattr(app.state, "deny_enabled", False),
        "path": DENYLIST_PATH,
        "loaded": bool(dg),
        "summary": dg.summary() if dg else None,
    }


@app.post("/debug/policy/test")
async def debug_policy_test(req: Request):
    """Test text against policy rules"""
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    text = (body.get("text") or "").strip()
    dg = getattr(app.state, "deny_guard", None)
    if not dg:
        return {"enabled": False, "hit": False}

    hit, cat, frag = dg.test_text(text)
    return {
        "enabled": getattr(app.state, "deny_enabled", False),
        "hit": hit,
        "category": cat,
        "fragment": frag,
    }


@app.post("/admin/policy/reload")
async def admin_policy_reload():
    """Reload policy rules (hot reload)"""
    try:
        app.state.deny_guard = DenyGuard.load_from_path(DENYLIST_PATH)
        print(
            f"[policy] reloaded {DENYLIST_PATH}:", app.state.deny_guard.summary()
        )
        return {"ok": True, "summary": app.state.deny_guard.summary()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ============================================================================
# Ollama Proxy Endpoints (with optional session persistence)
# ============================================================================

async def _fake_stream_from_full(payload_bytes: bytes):
    """Fallback: Get full response and convert to streaming format"""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
        async with session.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
        ) as response:
            text = await response.text()

    try:
        data = json.loads(text)
        full = (data.get("message") or {}).get("content") or data.get("response") or text
    except Exception:
        full = text

    async def gen():
        for i in range(0, len(full), 48):
            yield ndjson_line({"message": {"content": full[i : i + 48]}, "done": False})
            await asyncio.sleep(0.02)
        yield ndjson_line({"done": True})

    return gen


def _get_last_user_text(messages):
    """Extract last user message text"""
    for msg in reversed(messages or []):
        if (msg or {}).get("role") == "user":
            return msg.get("content") or ""
    return ""


@app.post("/api/chat")
async def proxy_ollama_chat(request: Request):
    """Proxy chat requests to Ollama with policy filtering and optional session persistence"""
    payload_bytes = await request.body()

    # Parse request body
    try:
        body = json.loads(payload_bytes.decode("utf-8"))
        want_stream = bool(body.get("stream", True))
        messages = body.get("messages") or []
    except Exception:
        want_stream = True
        messages = []

    # Optional session_id from query
    session_id = request.query_params.get("session_id")
    session_mode = bool(session_id)

    # Persist incoming messages when in session mode (append user/system for audit)
    if session_mode:
        for m in messages:
            role = (m or {}).get("role")
            if role in ("user", "system"):
                _append_history(session_id, role, (m.get("content") or ""))

    # Policy filtering setup
    dg = getattr(app.state, "deny_guard", None)
    deny_enabled = bool(getattr(app.state, "deny_enabled", False))
    refusal_text = (dg.refusal_text if dg else "抱歉，我無法回覆這個問題。")

    # Pre-request filtering
    hit_cat = None
    if deny_enabled and dg:
        hit, hit_cat, _frag = dg.test_text(_get_last_user_text(messages))
        if hit:
            headers = {
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Policy-Blocked": hit_cat or "1",
                "X-Policy-Triggered": "pre",
                "X-Session-Mode": "session" if session_mode else "stateless",
            }
            if want_stream:
                async def gen_refuse():
                    # also persist refusal if in session mode
                    if session_mode:
                        _append_history(session_id, "assistant", refusal_text)
                    yield ndjson_line({
                        "message": {"role": "assistant", "content": refusal_text},
                        "done": False,
                    })
                    yield ndjson_line({"done": True})

                return StreamingResponse(
                    gen_refuse(),
                    media_type="application/x-ndjson",
                    headers=headers,
                )
            else:
                if session_mode:
                    _append_history(session_id, "assistant", refusal_text)
                return JSONResponse(
                    {
                        "model": body.get("model"),
                        "message": {"role": "assistant", "content": refusal_text},
                        "done": True,
                    },
                    headers=headers,
                )

    # Setup HTTP session to upstream
    timeout = aiohttp.ClientTimeout(total=None, connect=10)
    connector = aiohttp.TCPConnector(force_close=False, enable_cleanup_closed=True)
    session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    try:
        if not want_stream:
            # Non-streaming response
            resp = await session.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                data=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
            )
            txt = await resp.text()
            await resp.release()
            await session.close()

            # Persist assistant reply if in session mode
            if session_mode:
                try:
                    data = json.loads(txt)
                    content = ((data.get("message") or {}).get("content")) or data.get("response") or ""
                except Exception:
                    content = ""
                if content:
                    _append_history(session_id, "assistant", content)

            return Response(
                content=txt,
                status_code=resp.status,
                media_type=resp.headers.get("Content-Type", "application/json"),
                headers={"X-Session-Mode": "session" if session_mode else "stateless"},
            )

        # Streaming response
        resp = await session.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
            allow_redirects=False,
        )

        if resp.status >= 400:
            err = await resp.read()
            await resp.release()
            await session.close()
            return Response(
                content=err,
                status_code=resp.status,
                media_type=resp.headers.get("Content-Type", "application/json"),
                headers={"X-Session-Mode": "session" if session_mode else "stateless"},
            )

        async def gen():
            got_any = False
            linebuf = ""
            assistant_buffer = []  # collect assistant content for persistence

            try:
                async for chunk in resp.content.iter_chunked(8192):
                    got_any = True
                    if await request.is_disconnected():
                        break
                    if not chunk:
                        continue

                    piece = chunk.decode("utf-8", "ignore")
                    linebuf += piece

                    # Process complete NDJSON lines
                    while True:
                        i = linebuf.find("\n")
                        if i < 0:
                            break
                        line = linebuf[:i]
                        linebuf = linebuf[i + 1 :]

                        # Content filtering during streaming
                        ls = line.strip()
                        if getattr(app.state, "deny_enabled", False) and getattr(app.state, "deny_guard", None) and ls.startswith("{"):
                            try:
                                obj = json.loads(ls)
                                content = ((obj.get("message") or {}).get("content")) or ""
                                if content:
                                    # collect for persistence
                                    if session_mode:
                                        assistant_buffer.append(content)
                                    hit, cat2, _ = app.state.deny_guard.test_text(content)
                                    if hit:
                                        # Policy violation: close upstream and return refusal
                                        try:
                                            await resp.release()
                                        except Exception:
                                            pass
                                        try:
                                            await session.close()
                                        except Exception:
                                            pass
                                        if session_mode:
                                            _append_history(session_id, "assistant", refusal_text)
                                        yield ndjson_line({
                                            "message": {"role": "assistant", "content": refusal_text},
                                            "done": False,
                                        })
                                        yield ndjson_line({"done": True})
                                        return
                            except Exception:
                                # If parsing fails, just forward it
                                pass
                        else:
                            # still try to accumulate assistant content when possible
                            try:
                                obj = json.loads(ls)
                                content = ((obj.get("message") or {}).get("content")) or ""
                                if content and session_mode:
                                    assistant_buffer.append(content)
                            except Exception:
                                pass

                        # Forward line as-is if no policy violation
                        yield (line + "\n").encode("utf-8")
                        await asyncio.sleep(0)

                # Handle remaining buffer content
                if linebuf:
                    ls = linebuf.strip()
                    if getattr(app.state, "deny_enabled", False) and getattr(app.state, "deny_guard", None) and ls.startswith("{"):
                        try:
                            obj = json.loads(ls)
                            content = ((obj.get("message") or {}).get("content")) or ""
                            if content and session_mode:
                                assistant_buffer.append(content)
                            hit, cat2, _ = app.state.deny_guard.test_text(content)
                            if hit:
                                try:
                                    await resp.release()
                                except Exception:
                                    pass
                                try:
                                    await session.close()
                                except Exception:
                                    pass
                                if session_mode:
                                    _append_history(session_id, "assistant", refusal_text)
                                yield ndjson_line({
                                    "message": {"role": "assistant", "content": refusal_text},
                                    "done": False,
                                })
                                yield ndjson_line({"done": True})
                                return
                        except Exception:
                            pass

                    # Forward remaining content
                    yield (linebuf + ("\n" if not linebuf.endswith("\n") else "")).encode("utf-8")

            except Exception as e:
                print("[llmtwins] stream error:", repr(e))
                traceback.print_exc()
                if not got_any:
                    try:
                        await resp.release()
                    except Exception:
                        pass
                    try:
                        await session.close()
                    except Exception:
                        pass
                    fake = await _fake_stream_from_full(payload_bytes)
                    async for c in fake():
                        # collect for persistence if possible (best-effort)
                        try:
                            obj = json.loads(c.decode("utf-8"))
                            content = ((obj.get("message") or {}).get("content")) or ""
                            if content and session_mode:
                                assistant_buffer.append(content)
                        except Exception:
                            pass
                        yield c
                else:
                    yield b'{"done": true}\n'
            finally:
                # Persist collected assistant text once per response
                if session_mode and assistant_buffer:
                    try:
                        _append_history(session_id, "assistant", "".join(assistant_buffer))
                    except Exception:
                        pass
                try:
                    await resp.release()
                except Exception:
                    pass
                try:
                    await session.close()
                except Exception:
                    pass

        # Return streaming response
        headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Mode": "session" if session_mode else "stateless",
        }
        if hit_cat:
            headers["X-Policy-Blocked"] = hit_cat
            headers["X-Policy-Triggered"] = "pre"

        return StreamingResponse(
            gen(),
            media_type=resp.headers.get("Content-Type", "application/x-ndjson"),
            headers=headers,
        )

    except Exception:
        # Connection error: fallback to fake streaming
        traceback.print_exc()
        try:
            await session.close()
        except Exception:
            pass
        fake = await _fake_stream_from_full(payload_bytes)
        return StreamingResponse(
            fake(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Session-Mode": "session" if session_mode else "stateless",
            },
        )

# ============================================================================
# Debug & Utility Endpoints
# ============================================================================

@app.get("/debug/config")
async def debug_config():
    """Get current configuration"""
    return {"OLLAMA_BASE_URL": OLLAMA_BASE_URL}


@app.get("/debug/upstream")
async def debug_upstream():
    """Test upstream Ollama connection"""
    async with httpx.AsyncClient(timeout=10, http2=False) as client:
        # Test GET /
        r = await client.get(f"{OLLAMA_BASE_URL}/")
        root_ok = (r.status_code == 200 and (r.text or "").strip() == "ok")

        # Test POST /api/chat (non-streaming)
        payload = {
            "model": "qwen2.5:7b-instruct",
            "stream": False,
            "messages": [
                {"role": "system", "content": "ping"},
                {"role": "user", "content": "回覆 OK 即可"},
            ],
        }
        r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)

        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}

        # Extract content preview
        preview = ""
        msg = data.get("message")
        if isinstance(msg, dict):
            preview = (msg.get("content") or "")[:50]
        elif isinstance(msg, str):
            preview = msg[:50]
        elif isinstance(data.get("response"), str):
            preview = data["response"][:50]

        return {
            "ok": r.status_code < 400,
            "base": OLLAMA_BASE_URL,
            "root_ok": root_ok,
            "status": r.status_code,
            "preview": preview,
        }


@app.get("/debug/pingstream")
async def pingstream():
    """Test streaming endpoint"""
    async def gen():
        for i in range(3):
            yield f'{{"ping":{i}}}\n'
            await asyncio.sleep(0.3)

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ============================================================================
# Session Management Endpoints
# ============================================================================

@app.post("/api/sessions")
async def create_session():
    """Create a new session and prepare directories for future uploads/history."""
    sid = "sess_" + uuid.uuid4().hex
    d = _session_dir(sid)
    _ensure_dir(d / "raw")
    _ensure_dir(d / "config")
    _ensure_dir(d / "state")
    _ensure_dir(d / "artifacts")

    # 生成 effective template（你已經有 _init_session_files）
    init_res = _init_session_files(sid, model="project")

    # 初始化對話狀態
    try:
        st = app.state.state_store.init_session(sid)
    except Exception as e:
        st = {"error": f"state init failed: {e}"}

    return {"session_id": sid, "init": init_res, "state": st}

def _parse_first_pdf_and_write(session_id: str) -> dict:
    """
    委派給 app.pdf_ingest 模組；此函式僅負責：
      - 呼叫 ingest
      - 更新 state
      - 寫入簡短 system log
    """
    from app.pdf_ingest import ingest_first_pdf_and_write_parsed, list_required_fields
    res = ingest_first_pdf_and_write_parsed(
        session_id=session_id,
        sess_base=SESS_BASE,
        base_dir=BASE_DIR,
        model="project",
    )

    if not res.ok:
        return {"ok": False, "error": res.error or "ingest failed"}

    # required fields
    try:
        pending_fields = list_required_fields(BASE_DIR, model="project")
    except Exception as e:
        pending_fields = []
        print("[state] list_required_fields error:", e)

    # 更新 state
    try:
        app.state.state_store.mark_parsed(
            session_id,
            filename=res.filename,
            pages=res.pages,
            pending_fields=pending_fields,
        )
    except Exception as e:
        print("[state] mark_parsed error:", e)

    # 系統訊息
    try:
        ocr_tag = f", ocr_used={res.ocr_used}, ocr_quality={res.ocr_quality or '-'}"
        _append_history(session_id, "system",
                        f"[parsed] {res.filename} → artifacts/parsed.json (pages={res.pages}, chunks={res.chunks}{ocr_tag})")
    except Exception:
        pass

    return {"ok": True, "pages": res.pages, "chunks": res.chunks, "filename": res.filename}

# ===== PDF 解析與安全切塊（v0.1，無 OCR/RAG）=====
import os, re, glob, json
from datetime import datetime, timezone
from pdfminer.high_level import extract_text
import yaml

SAFE_CHUNK_SIZE = 1200   # 每塊上限字元
SAFE_OVERLAP    = 120    # 塊間重疊

def _clean_text(s: str) -> str:
    s = s.replace("\x00", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\r\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _paragraph_split(s: str):
    parts = [p.strip() for p in s.split("\n\n") if p.strip()]
    return parts if len(parts) > 2 else [s]

def _make_chunks(text: str, page: int, base_id: str):
    chunks = []
    if not text.strip():
        return chunks
    paras = _paragraph_split(text)
    buf = ""
    start_idx = 0
    cid = 1
    for para in paras:
        add = (buf + ("\n\n" if buf else "") + para).strip()
        if len(add) <= SAFE_CHUNK_SIZE:
            buf = add
            continue
        if buf:
            end_idx = start_idx + len(buf)
            chunks.append({"id": f"{base_id}c{cid}", "page": page,
                           "start_char": start_idx, "end_char": end_idx, "text": buf})
            cid += 1
            keep = buf[-SAFE_OVERLAP:] if len(buf) > SAFE_OVERLAP else buf
            buf = (keep + "\n\n" + para).strip()
            start_idx = end_idx - len(keep)
        else:
            long = para
            pos = 0
            while pos < len(long):
                piece = long[pos:pos+SAFE_CHUNK_SIZE]
                end_idx = start_idx + len(piece)
                chunks.append({"id": f"{base_id}c{cid}", "page": page,
                               "start_char": start_idx, "end_char": end_idx, "text": piece})
                cid += 1
                pos += SAFE_CHUNK_SIZE - SAFE_OVERLAP
                start_idx = end_idx - SAFE_OVERLAP
            buf = ""
            start_idx += SAFE_OVERLAP
    if buf:
        end_idx = start_idx + len(buf)
        chunks.append({"id": f"{base_id}c{cid}", "page": page,
                       "start_char": start_idx, "end_char": end_idx, "text": buf})
    return chunks

def _extract_pages_text(pdf_path: str):
    full = extract_text(pdf_path) or ""
    # pdfminer 會用 \x0c 當分頁；沒有就當單頁
    pages = [p for p in full.split("\x0c") if p.strip()] or [full]
    return [_clean_text(p) for p in pages]

def _pending_fields_from_catalog(model: str = "project"):
    """讀 configs/field_catalogs/{model}.yaml → 回傳必填欄位清單"""
    path = BASE_DIR / f"configs/field_catalogs/{model}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    fields = (cfg.get("fields") or {}).items()
    required = [name for name, spec in fields if (spec or {}).get("required") is True]
    return required

@app.post("/api/sessions/{session_id}/upload")
async def upload_to_session(
    session_id: str,
    file: UploadFile = File(...),
    auto_parse: bool = Query(True, description="是否自動解析 PDF 並更新 state")
):
    """
    Upload a file into a session. The file will be stored under sessions/<sid>/raw/.
    Returns metadata, and optionally triggers parse->artifacts/parsed.json.
    """
    d = _session_dir(session_id)
    raw_dir = d / "raw"
    _ensure_dir(raw_dir)

    orig_name = (file.filename or "upload.bin")
    orig_name = Path(orig_name).name
    suffix = Path(orig_name).suffix.lower()

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

    # 把上傳事件寫進 chat_history
    try:
        _append_history(session_id, "system", f"[upload] {orig_name} -> raw/{dest_name} ({size} bytes)")
    except Exception:
        pass

    # 如果是 PDF 且 auto_parse=true，就立即解析
    parse_result = None
    if suffix == ".pdf" and auto_parse:
        try:
            parse_result = _parse_first_pdf_and_write(session_id)
        except Exception as e:
            parse_result = {"ok": False, "error": f"parse failed: {e}"}

    return {
        "ok": True,
        "session_id": session_id,
        "name": orig_name,
        "stored_as": dest_name,
        "size": size,
        "mime": file.content_type,
        "path": str(dest_path.relative_to(SESS_BASE)),
        "parse": parse_result,
    }

from fastapi import HTTPException

@app.get("/api/sessions/{session_id}/state")
async def get_session_state(session_id: str):
    """
    回傳 sessions/<sid>/state/conversation_state.json 的內容
    """
    try:
        st = app.state.state_store.get(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"state error: {e}")

    if not st:
        # 可能 session 不存在、或尚未 init_session
        raise HTTPException(status_code=404, detail="state not found")

    return {"ok": True, "state": st}
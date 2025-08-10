import json
import os
import asyncio
import traceback
from pathlib import Path

import aiohttp
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Local imports
from database import (
    initDB, selectFromDB, deleteFromDB, listFromDB,
    insertOrUpdateProfile, insertOrUpdateAPITable
)
from models import regUser, getUser, prompt, callback_api
from LLM.LLMTwins import DigitalTwins
from policy.guard import DenyGuard

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

# FastAPI app initialization
app = FastAPI()

# CORS configuration
ALLOWED_ORIGINS = [
    "https://eva.4impact.cc",
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Consider using ALLOWED_ORIGINS for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
conn, cursor = initDB()

# ============================================================================
# Startup Events & Policy Loading
# ============================================================================

@app.on_event("startup")
async def load_policy_on_startup():
    """Load policy guard on startup"""
    try:
        app.state.deny_guard = DenyGuard.load_from_path(DENYLIST_PATH)
        app.state.deny_enabled = DENY_ENABLED
        print(f"[policy] loaded {DENYLIST_PATH}:",
              app.state.deny_guard.summary(),
              "enabled=", app.state.deny_enabled)
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
        "fragment": frag
    }

@app.post("/admin/policy/reload")
async def admin_policy_reload():
    """Reload policy rules (hot reload)"""
    try:
        app.state.deny_guard = DenyGuard.load_from_path(DENYLIST_PATH)
        print(f"[policy] reloaded {DENYLIST_PATH}:",
              app.state.deny_guard.summary())
        return {"ok": True, "summary": app.state.deny_guard.summary()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ============================================================================
# Digital Twins Management Endpoints
# ============================================================================

@app.post("/register_llm_twins")
async def register_llm_twins(user: regUser):
    """Register or update LLM digital twins"""
    # Check if user is already registered
    result = selectFromDB(conn, "llm_twins", "name", user.name)

    # Register or update digital twins
    dt = DigitalTwins()
    result, profile, api_table = dt.register_llm_twins(user.name, user.description)

    # Insert or update profile
    if result:
        result = insertOrUpdateProfile(conn, "llm_twins", "name", user.name, profile)

    # Insert or update API table
    if result:
        result = insertOrUpdateAPITable(conn, "llm_twins_api", "name", user.name, api_table)

    # Return Profile & API Table
    profile["api_table"] = api_table
    return profile

@app.post("/get_llm_twins")
async def get_llm_twins(user: getUser):
    """Get LLM digital twins by user name"""
    result = selectFromDB(conn, "llm_twins", "name", user.name)
    
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Digital Twin for this user is not registered"
        )
    
    return {"result": result}

@app.post("/get_llm_twins_api")
async def get_llm_twins_api(user: getUser):
    """Get digital twins API table"""
    result = selectFromDB(conn, "llm_twins_api", "name", user.name)
    
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Digital Twin for this user is not registered"
        )
    
    return {"result": json.loads(result[1])}

@app.post("/delete_llm_twins")
async def delete_llm_twins(user: getUser):
    """Delete LLM digital twins by user name"""
    result = deleteFromDB(conn, "llm_twins", "name", user.name)
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Digital Twin for this user is not registered"
        )
    
    return {"message": "Digital Twin for this user has been deleted"}

@app.get("/list_llm_twins")
async def list_llm_twins():
    """List all LLM digital twins"""
    result = listFromDB(conn, "llm_twins")
    return {"result": result}

# ============================================================================
# LLM Processing Endpoints
# ============================================================================

@app.post("/prompt")
async def handle_prompt(prompt_data: prompt):
    """Handle prompt processing with intent recognition"""
    # Get user profile from database
    profile = selectFromDB(conn, "llm_twins", "name", prompt_data.role)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Digital Twin for this user is not registered"
        )

    # Get API table from database
    api_table = selectFromDB(conn, "llm_twins_api", "name", prompt_data.role)
    if api_table is None:
        raise HTTPException(
            status_code=404,
            detail="API table for this user is not registered"
        )

    # Process prompt
    dt = DigitalTwins()
    dt.set_model(prompt_data.model if prompt_data.model is not None else None)
    result, message = dt.prompt(profile, prompt_data)
    
    return {"result": result, "message": message}

@app.post("/callbacks")
async def handle_callbacks(callback_data: callback_api):
    """Handle callback API requests"""
    # Get user profile from database
    profile = selectFromDB(conn, "llm_twins", "name", callback_data.role)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Digital Twin for this user is not registered"
        )

    # Run callback function
    dt = DigitalTwins()
    result = dt.callback(callback_data.message)
    
    return {"result": result}

# ============================================================================
# Ollama Proxy Endpoints
# ============================================================================

async def _fake_stream_from_full(payload_bytes: bytes):
    """Fallback: Get full response and convert to streaming format"""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
        async with session.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "Accept-Encoding": "identity"
            }
        ) as response:
            text = await response.text()
    
    try:
        data = json.loads(text)
        full = (data.get("message") or {}).get("content") or data.get("response") or text
    except Exception:
        full = text

    async def gen():
        for i in range(0, len(full), 48):
            yield ndjson_line({
                "message": {"content": full[i:i+48]},
                "done": False
            })
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
    """Proxy chat requests to Ollama with policy filtering"""
    payload_bytes = await request.body()

    # Parse request body
    try:
        body = json.loads(payload_bytes.decode("utf-8"))
        want_stream = bool(body.get("stream", True))
        messages = body.get("messages") or []
    except Exception:
        want_stream = True
        messages = []

    # Policy filtering setup
    dg = getattr(app.state, "deny_guard", None)
    deny_enabled = bool(getattr(app.state, "deny_enabled", False))
    refusal_text = (dg.refusal_text if dg else "抱歉，我無法回覆這個問題。")

    # Pre-request filtering
    hit_cat = None
    if deny_enabled and dg:
        hit, hit_cat, _frag = dg.test_text(_get_last_user_text(messages))
        if hit:
            if want_stream:
                async def gen_refuse():
                    yield ndjson_line({
                        "message": {"role": "assistant", "content": refusal_text},
                        "done": False
                    })
                    yield ndjson_line({"done": True})
                
                return StreamingResponse(
                    gen_refuse(),
                    media_type="application/x-ndjson",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                        "X-Policy-Blocked": hit_cat or "1",
                        "X-Policy-Triggered": "pre"
                    },
                )
            else:
                return JSONResponse(
                    {
                        "model": body.get("model"),
                        "message": {"role": "assistant", "content": refusal_text},
                        "done": True,
                    },
                    headers={
                        "X-Policy-Blocked": hit_cat or "1",
                        "X-Policy-Triggered": "pre"
                    },
                )

    # Setup HTTP session
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
            return Response(
                content=txt,
                status_code=resp.status,
                media_type=resp.headers.get("Content-Type", "application/json"),
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
            )

        async def gen():
            got_any = False
            linebuf = ""

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
                        linebuf = linebuf[i+1:]

                        # Content filtering during streaming
                        ls = line.strip()
                        if deny_enabled and dg and ls.startswith("{"):
                            try:
                                obj = json.loads(ls)
                                content = ((obj.get("message") or {}).get("content")) or ""
                                if content:
                                    hit, cat2, _ = dg.test_text(content)
                                    if hit:
                                        # Policy violation: close upstream and return refusal
                                        try:
                                            await resp.release()
                                        except:
                                            pass
                                        try:
                                            await session.close()
                                        except:
                                            pass
                                        yield ndjson_line({
                                            "message": {"role": "assistant", "content": refusal_text},
                                            "done": False
                                        })
                                        yield ndjson_line({"done": True})
                                        return
                            except Exception:
                                pass

                        # Forward line as-is if no policy violation
                        yield (line + "\n").encode("utf-8")
                        await asyncio.sleep(0)

                # Handle remaining buffer content
                if linebuf:
                    ls = linebuf.strip()
                    if deny_enabled and dg and ls.startswith("{"):
                        try:
                            obj = json.loads(ls)
                            content = ((obj.get("message") or {}).get("content")) or ""
                            if content:
                                hit, cat2, _ = dg.test_text(content)
                                if hit:
                                    try:
                                        await resp.release()
                                    except:
                                        pass
                                    try:
                                        await session.close()
                                    except:
                                        pass
                                    yield ndjson_line({
                                        "message": {"role": "assistant", "content": refusal_text},
                                        "done": False
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
                    except:
                        pass
                    try:
                        await session.close()
                    except:
                        pass
                    fake = await _fake_stream_from_full(payload_bytes)
                    async for c in fake():
                        yield c
                else:
                    yield b'{"done": true}\n'
            finally:
                try:
                    await resp.release()
                except:
                    pass
                try:
                    await session.close()
                except:
                    pass

        # Return streaming response
        headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
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
        except:
            pass
        fake = await _fake_stream_from_full(payload_bytes)
        return StreamingResponse(
            fake(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

# ============================================================================
# Debug Endpoints
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
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
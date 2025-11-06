# app/routers/debug.py
import asyncio, json
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/config")
async def debug_config(request: Request):
    return {"OLLAMA_BASE_URL": request.app.state.ollama_base_url}

@router.get("/upstream")
async def debug_upstream(request: Request):
    base = request.app.state.ollama_base_url
    async with httpx.AsyncClient(timeout=10, http2=False) as client:
        r = await client.get(f"{base}/")
        root_ok = (r.status_code == 200 and (r.text or "").strip() == "ok")
        payload = {
            "model": "openai/gpt-4o-mini",
            "stream": False,
            "messages": [
                {"role": "system", "content": "ping"},
                {"role": "user", "content": "回覆 OK 即可"},
            ],
        }
        r = await client.post(f"{base}/api/chat", json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
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
            "base": base,
            "root_ok": root_ok,
            "status": r.status_code,
            "preview": preview,
        }

@router.get("/policy")
async def debug_policy(request: Request):
    dg = getattr(request.app.state, "deny_guard", None)
    return {
        "enabled": getattr(request.app.state, "deny_enabled", False),
        "path": getattr(request.app.state, "denylist_path", None),
        "loaded": bool(dg),
        "summary": dg.summary() if dg else None,
    }

@router.post("/policy/test")
async def debug_policy_test(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    text = (body.get("text") or "").strip()
    dg = getattr(request.app.state, "deny_guard", None)
    if not dg:
        return {"enabled": False, "hit": False}
    hit, cat, frag = dg.test_text(text)
    return {
        "enabled": getattr(request.app.state, "deny_enabled", False),
        "hit": hit,
        "category": cat,
        "fragment": frag,
    }

@router.get("/pingstream")
async def pingstream():
    async def gen():
        for i in range(3):
            yield f'{{"ping":{i}}}\n'
            await asyncio.sleep(0.3)
    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

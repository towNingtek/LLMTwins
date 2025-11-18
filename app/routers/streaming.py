import os
import json
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from core.role_profiles import load_role_profile

router = APIRouter(prefix="/stream", tags=["stream"])

base_url = os.getenv("OLLAMA_GATEWAY_URL").rstrip("/")
chat_url = f"{base_url}/api/chat"


async def llm_stream(payload: dict):
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", chat_url, json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    yield (line + "\n").encode()
    

@router.post("/{role_name}")
async def stream_role(role_name: str, request: Request):

    body = await request.json()
    user_msg = body.get("message")
    if not user_msg:
        raise HTTPException(400, "message is required")

    profile = load_role_profile(role_name)

    payload = {
        "model": profile.get("model", "openai/gpt-4o-mini"),
        "stream": True,
        "messages": [
            {"role": "system", "content": profile["system_prompt"]},
            {"role": "user", "content": user_msg},
        ],
        "options": {"temperature": profile.get("temperature", 0.5)}
    }

    return StreamingResponse(
        llm_stream(payload),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

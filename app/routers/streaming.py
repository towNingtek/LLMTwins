# app/routers/streaming.py
import json
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/stream", tags=["stream"])


LLM_GATEWAY_URL = "http://localhost:8002/api/chat"


async def llm_stream(payload: dict):
    """
    Proxy 上游 NDJSON Streaming
    回傳一個 async generator
    """
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", LLM_GATEWAY_URL, json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue

                # 直接逐行轉發
                yield (line + "\n").encode("utf-8")


@router.post("/{role_name}")
async def stream_role(role_name: str, request: Request):
    """
    例如：
    POST /stream/ai_cat
    body: { "message": "嗨 你是誰？" }
    """

    body = await request.json()
    user_msg = body.get("message") or ""

    # 每個角色各自有風格 → 系統 prompt 寫在這裡
    if role_name == "ai_cat":
        system_prompt = "你是一隻可愛的 AI 貓咪，用台灣繁體中文回覆，語氣像貼圖貓咪一樣可愛喵～"
    else:
        system_prompt = "你是一個友善的 AI 助理。"

    payload = {
        "model": "openai/gpt-4o-mini",
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
    }

    # 返回 StreamingResponse
    return StreamingResponse(
        llm_stream(payload),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


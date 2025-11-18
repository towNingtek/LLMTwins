# core/llm_clients.py
import os
import httpx
import json
from typing import AsyncGenerator

base_url = os.getenv("OLLAMA_GATEWAY_URL").rstrip("/")
chat_url = f"{base_url}/api/chat"

async def chat(model, messages, stream=False, temperature=0.3):
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": temperature},
    }

    if not stream:
        async with httpx.AsyncClient() as client:
            resp = await client.post(chat_url, json=payload)
            data = resp.json()
            return data["message"]

    async def stream_generator() -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", chat_url, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        msg = obj.get("message", {})
                        content = msg.get("content")
                        if content:
                            yield content
                    except:
                        continue

    return stream_generator()
# core/llm_clients.py
import httpx
import os
import json
from typing import AsyncGenerator, List, Any

OLLAMA_GATEWAY_URL = os.getenv("OLLAMA_GATEWAY_URL", "http://localhost:8002")


def convert_messages(raw_messages: List[Any]):
    out = []
    for m in raw_messages:
        if isinstance(m, dict) and "role" in m and "content" in m:
            out.append(m)
        else:
            out.append({"role": "user", "content": str(m)})
    return out


async def stream_ollama(messages, model="openai/gpt-4o-mini"):
    body = {
        "model": model,
        "stream": True,
        "messages": messages
    }

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{OLLAMA_GATEWAY_URL}/api/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    yield line

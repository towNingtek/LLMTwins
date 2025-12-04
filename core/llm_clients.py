# core/llm_clients.py
import httpx
import os
import json
from typing import AsyncGenerator, List, Any

from dotenv import load_dotenv
load_dotenv()

# Gateway URL（Suport Ollama Gateway / OpenAI Gateway）
OLLAMA_GATEWAY_URL = os.getenv("OLLAMA_GATEWAY_URL", "http://localhost:8082")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8002")


# ============================================================
# Utility
# ============================================================

def convert_messages(raw_messages: List[Any]):
    """
    Unify messages into the OpenAI standard format:
    [{"role": "...", "content": "..."}]
    """
    out = []
    for m in raw_messages:
        if isinstance(m, dict) and "role" in m and "content" in m:
            out.append(m)
        else:
            out.append({"role": "user", "content": str(m)})
    return out


# ============================================================
# OpenAI-format Streaming Gateway (NDJSON)
# ============================================================

async def stream_openai(model, messages, tools=None, options=None):
    body = {
        "model": model,
        "stream": True,
        "messages": convert_messages(messages),
    }

    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    if options:
        body.update(options)

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{OLLAMA_GATEWAY_URL}/api/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    yield line


# ============================================================
# Ollama Gateway (OpenAI 格式)
# ============================================================

async def stream_ollama(
    model: str,
    messages: List[Any],
    tools: list | None = None,
) -> AsyncGenerator[str, None]:
    
    body = {
        "model": model,
        "stream": True,
        "messages": convert_messages(messages),
    }

    if tools:
        body["tools"] = tools

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_GATEWAY_URL}/api/chat",
            json=body
        ) as resp:
            
            async for line in resp.aiter_lines():
                if line:
                    yield line  # 再交給 LLMTwins runtime



# ============================================================
# Minimal LLMClient（供 runtime 使用）
# ============================================================

class LLMClient:
    """
    The LLMTwins runtime calls `.stream()`.
    Here, we uniformly support openai/xxx and others (considered as Ollama).
    """

    async def stream(
        self,
        model: str,
        messages: List[Any],
        temperature: float = 0.3,
        tools: List[Any] | None = None,
        options: dict | None = None,
    ) -> AsyncGenerator[str, None]:

        # OpenAI
        if model.startswith("openai/"):
            async for line in stream_openai(
                model=model,
                messages=messages,
                options=options,
                tools=tools,
            ):
                yield line
            return

        # 其它 → Ollama Gateway
        async for line in stream_ollama(
            model=model,
            messages=messages,
            tools=tools,
        ):
            yield line


# 單例
_llm_client_instance = LLMClient()

def get_llm_client(model: str) -> LLMClient:
    return _llm_client_instance
# clients/ollama_client.py
import os, json, asyncio
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_AUTH = os.getenv("OLLAMA_AUTH", None)  # e.g. "Bearer xxx"

def _headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if OLLAMA_AUTH:
        h["Authorization"] = OLLAMA_AUTH
    return h

async def stream_chat(model: str,
                      messages: List[Dict[str, str]],
                      options: Optional[Dict[str, Any]] = None
                      ) -> AsyncGenerator[Dict[str, Any], None]:
    """
    轉發到 /api/chat 並以「統一格式」回傳增量:
    yield {"type":"delta", "text":"..."} or {"type":"done", "usage": {...}}
    """
    payload = {"model": model, "messages": messages, "stream": True}
    if options:
        payload["options"] = options

    timeout = httpx.Timeout(None, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST",
                                 f"{OLLAMA_BASE_URL}/api/chat",
                                 headers=_headers(),
                                 json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                # 兩種情況：增量 or 完成
                if data.get("done"):
                    # Ollama 在結尾會提供評估統計
                    usage = {
                        "prompt_eval_count": data.get("prompt_eval_count"),
                        "eval_count": data.get("eval_count"),
                        "total_duration": data.get("total_duration"),
                    }
                    yield {"type": "done", "usage": usage}
                    break

                # 增量內容：chat 用 message.content；generate 用 response
                txt = (data.get("message", {}) or {}).get("content") or data.get("response") or ""
                if txt:
                    yield {"type": "delta", "text": txt}

async def nonstream_chat(model: str,
                         messages: List[Dict[str, str]],
                         options: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
    payload = {"model": model, "messages": messages, "stream": False}
    if options:
        payload["options"] = options

    timeout = httpx.Timeout(300.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{OLLAMA_BASE_URL}/api/chat",
                              headers=_headers(), json=payload)
        r.raise_for_status()
        data = r.json()
        # Ollama 非流回應會把完整內容放在 message.content
        text = (data.get("message") or {}).get("content") or data.get("response") or ""
        return {"text": text, "raw": data}
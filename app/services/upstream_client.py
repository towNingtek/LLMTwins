# app/services/upstream_client.py
# import json, aiohttp, asyncio
# from typing import List, Tuple, Dict, Any
"""
async def ask_upstream_json(
    base_url: str,
    model: str,
    messages: List[Dict[str, str]],
    timeout_s: int,
) -> Tuple[bool, str]:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s, connect=10)) as s2:
            payload: Dict[str, Any] = {"model": model, "stream": False, "messages": messages}
            async with s2.post(
                f"{base_url}/api/chat",
                data=json.dumps(payload, ensure_ascii=False),
                headers={"Content-Type": "application/json", "Accept-Encoding": "identity"},
            ) as r2:
                txt = await r2.text()
        return True, txt
    except asyncio.TimeoutError:
        return False, "timeout"
    except Exception as e:
        return False, f"error: {e}"
"""
# app/core/ndjson.py
import json
from typing import AsyncGenerator, Dict

def ndjson_line(obj: Dict) -> bytes:
    """將物件序列化為 NDJSON 一行（bytes）"""
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

def one_shot_ndjson(text: str):
    """回傳一個 async 產生器，先送一行訊息、再送 done=true。"""
    async def gen() -> AsyncGenerator[bytes, None]:
        yield ndjson_line({"message": {"role": "assistant", "content": text}, "done": False})
        yield ndjson_line({"done": True})
    return gen

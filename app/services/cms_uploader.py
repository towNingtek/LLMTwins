# app/services/cms_uploader.py
import json
import aiohttp
from typing import Tuple, Dict, Any

def format_payload_for_cms(payload: Dict[str, Any]) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for k, v in (payload or {}).items():
        if k == "weight_description" and not isinstance(v, str):
            data[k] = json.dumps(v or {}, ensure_ascii=False)
        elif v is None:
            data[k] = ""
        else:
            data[k] = str(v)
    return data

async def post_cms_upload(payload: Dict[str, Any], upload_url: str) -> Tuple[int, Dict[str, Any], str]:
    data = format_payload_for_cms(payload)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
        async with s.post(upload_url, data=data) as r:
            raw = await r.text()
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {}
            return r.status, parsed, raw
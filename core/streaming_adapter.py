# core/streaming_adapter.py
import json
from typing import Any, AsyncGenerator, Dict


def event_to_ndjson_obj(event: Any) -> Dict[str, Any] | None:
    """
    把 LangGraph 的 astream event -> 轉成一個「可被 json.dumps」的物件。

    目前先支援你現有的情境：
      event 類似：{"respond": {"message": "喵～你好呀！"}}

    未來如果你在 node 裡面做 token 級 yield，只要維持這個結構，
    這個 adapter 就會一行一行吐出 NDJSON。
    """
    if not isinstance(event, dict):
        # 極簡 fallback：直接當成一段文字
        return {"type": "message", "content": str(event)}

    # 1) 你現在 ai_cat 的輸出：{"respond": {...}}
    if "respond" in event and isinstance(event["respond"], dict):
        node_output = event["respond"]
        text = (
            node_output.get("message")
            or node_output.get("content")
            or node_output.get("text")
        )
        if text:
            return {
                "type": "message",   # 先用 message，之後你要拆 token 再改 type=token 也行
                "content": text,
            }

    # 2) 預留其他形式，例如 {"llm_content": "..."} 之類，可以日後擴充
    if "llm_content" in event:
        return {
            "type": "message",
            "content": str(event["llm_content"]),
        }

    # 3) fallback：把整個 event 打包丟出去（方便 debug）
    try:
        return {
            "type": "event",
            "content": event,
        }
    except Exception:
        return None


async def astream_to_ndjson(
    workflow: Any,
    workflow_input: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    """
    將 workflow.astream(...) 包成 NDJSON stream。

    每個 event -> 0~1 行 JSON
    最後會補上一行 {"type":"done"}。
    """
    async for event in workflow.astream(workflow_input):
        obj = event_to_ndjson_obj(event)
        if obj is None:
            continue

        line = json.dumps(obj, ensure_ascii=False)
        # NDJSON = 一行一個 JSON
        yield line + "\n"

    # 結束訊號
    done_line = json.dumps({"type": "done"}, ensure_ascii=False)
    yield done_line + "\n"

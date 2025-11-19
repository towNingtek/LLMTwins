# roles/ai_cat/nodes/respond_llm.py
import json
from typing import Dict, Any, AsyncGenerator
from langchain_core.runnables import RunnableConfig
from core.llm_clients import stream_ollama


async def respond_llm_node(state: 'CatState', config: RunnableConfig) -> AsyncGenerator[Dict[str, Any], None]:
    """
    LLM Streaming Node：同時支援 tool_call
    """

    # 加上 profile.yaml 的 system prompt
    system_msg = {
        "role": "system",
        "content": state.system_prompt
    }

    raw_messages = [system_msg] + state.messages
    final_text = ""

    # ===== STREAM LLM =====
    async for line in stream_ollama(
        raw_messages,
        model=state.model,
        tools=state.tools  # <--- 關鍵：傳工具給 LLM
    ):
        try:
            obj = json.loads(line)

            # 1) Tool Call（模型要呼叫工具）
            tool_call = (
                obj.get("message", {}).get("tool_call") or
                obj.get("choices", [{}])[0].get("delta", {}).get("tool_call")
            )
            if tool_call:
                yield {"tool_call": tool_call}
                return

            # 2) 普通 token
            content = (
                obj.get("message", {}).get("content") or
                obj.get("choices", [{}])[0].get("delta", {}).get("content")
            )

        except Exception:
            continue

        if content:
            final_text += content
            yield {"respond": {"token": content}}

    yield {
        "output": final_text,
        "respond": None
    }

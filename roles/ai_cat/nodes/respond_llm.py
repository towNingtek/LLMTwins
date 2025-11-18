# roles/ai_cat/nodes/respond_llm.py
import json
from core.llm_clients import stream_ollama
from roles.ai_cat.state import CatState

async def respond_llm_node(state: CatState) -> CatState:

    raw_messages = state.messages

    final_text = ""

    async for line in stream_ollama(raw_messages):
        try:
            obj = json.loads(line)
        except:
            continue

        msg = obj.get("message")
        if msg and msg.get("content"):
            final_text += msg["content"]

    return CatState(
        model=state.model,
        messages=state.messages,
        output=final_text
    )

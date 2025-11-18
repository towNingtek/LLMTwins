# roles/ai_cat/nodes/respond_llm.py
import json
from core.llm_clients import stream_ollama
from typing import Dict, Any, AsyncGenerator
from langchain_core.runnables import RunnableConfig


async def respond_llm_node(state: 'CatState', config: RunnableConfig) -> AsyncGenerator[Dict[str, Any], None]:
    """
    LLMTwins 用的串流節點：
    - 自動帶入 profile.yaml 的 system_prompt
    - 只做串流，不做 channel_writer
    - 保持 yield {"respond": {"token": ...}}
    """

    # 動態從 profile.yaml 載入角色人設
    system_msg = {
        "role": "system",
        "content": state.system_prompt  # <-- 關鍵：來自 profile.yaml
    }

    # 正確組裝 messages
    raw_messages = [system_msg] + state.messages

    final_text = ""

    # ======= 串流主體 =======    
    async for line in stream_ollama(raw_messages, model=state.model):
        try:
            obj = json.loads(line)

            # 嘗試取得 content（OpenAI / Ollama 兩種 JSON 格式兼容）
            content = (
                obj.get("message", {}).get("content") or
                obj.get("choices", [{}])[0].get("delta", {}).get("content")
            )

        except Exception:
            continue

        # ======= 串流 token =======
        if content:
            final_text += content
            yield {
                "respond": {
                    "token": content
                }
            }

    # ======= 最終輸出 =======
    yield {
        "output": final_text,
        "respond": None
    }

import json
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, SystemMessage
from core.llm_clients import stream_ollama
from langchain_core.callbacks.manager import adispatch_custom_event

async def analyze_node(state: 'CatState', config: RunnableConfig) -> Dict[str, Any]:
    """
    Analysis Node: Before performing the main task, analyze the user's problem
    This node will output the thought process
    """

    # Preparation Analysis prompt
    system_msg = SystemMessage(content="你是一個分析助手，用繁體中文簡短分析用戶的問題意圖（1-2句話）。")

    # The last question about acquiring users
    user_messages = [m for m in state.messages if hasattr(m, 'type') and m.type == 'human']
    if user_messages:
        last_user_msg = user_messages[-1]
        analysis_messages = [
            system_msg,
            last_user_msg
        ]
    else:
        return {
            "messages": [AIMessage(content="")],
            "next": "respond_llm"
        }

    final_text = ""

    # Analysis using LLM
    async for line in stream_ollama(
        messages=analysis_messages,
        model=state.model,
        tools=[]
    ):
        try:
            obj = json.loads(line)

            msg_dict = obj.get("message", {})
            choice_delta = obj.get("choices", [{}])[0].get("delta", {})

            # Check content
            content = msg_dict.get("content") or choice_delta.get("content")

            if content:
                final_text += content

                # Send a custom event "store_token" and mark it as being in the analyze phase
                await adispatch_custom_event(
                    "store_token",
                    {"chunk": content, "stage": "analyze"},
                    config=config
                )

        except Exception as e:
            print(f"⚠️ [Error] Error parsing line: {e}")
            continue


    # Return the analysis results and continue to respond_llm
    return {
        "messages": [AIMessage(content=f"[分析] {final_text}")],
        "next": "respond_llm"
    }
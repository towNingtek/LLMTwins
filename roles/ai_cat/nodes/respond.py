# roles/ai_cat/nodes/respond.py
from core.llm_clients import chat_stream

async def respond_node(state):
    """
    LangGraph 1.x async streaming node
    正確寫法：
    - 不 return
    - 不 await chat_stream()
    - 必須 async for + yield event
    """

    user_msg = state.message
    model = "gpt-4o-mini"

    messages = [
        {"role": "system", "content": "你是可愛的喵系助理，回答保持喵語調"},
        {"role": "user", "content": user_msg},
    ]

    async for token in chat_stream(model, messages):
        yield {
            "respond": {
                "token": token
            }
        }
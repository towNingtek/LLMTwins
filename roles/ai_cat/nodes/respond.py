from core.llm_clients import chat

async def respond_node(state, profile):
    user_msg = state.message

    messages = [
        {"role": "system", "content": profile["system_prompt"]},
        {"role": "user", "content": user_msg},
    ]

    reply = ""

    gen = await chat(
        model=profile.get("model", "openai/gpt-4o-mini"),
        messages=messages,
        stream=True,
        temperature=profile.get("temperature", 0.5),
    )

    async for token in gen:
        reply += token

    return {
        "message": reply,
        "mood": "happy"
    }

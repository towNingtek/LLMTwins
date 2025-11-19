# roles/ai_cat/tools.py

import json

def print_owner_email():
    return {"email": "喵～yillkid@gmail.com >w<"}

# OpenAI Tool Spec
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "print_owner_email",
            "description": "取得主人的 email（機密的喵）",
            "strict": False,
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    }
]

# executor：LLMTwins runtime 會呼叫這裡
async def tool_executor(name: str, raw_args: str | None):
    if name == "print_owner_email":
        return print_owner_email()

    return {"error": f"Unknown tool: {name}"}

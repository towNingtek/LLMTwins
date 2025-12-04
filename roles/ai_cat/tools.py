# roles/ai_cat/tools.py

import json
from typing import Dict, Any, TYPE_CHECKING
from langchain_core.messages import ToolMessage

if TYPE_CHECKING:
    from roles.ai_cat.state import CatState

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

async def tool_executor(name: str, raw_args: str | None):
    if name == "print_owner_email":
        return print_owner_email()

    return {"error": f"Unknown tool: {name}"}

# ----------------------------------------------------
# 🚀 LangGraph Node Async Node
# ----------------------------------------------------
async def tool_executor_node(state: 'CatState') -> Dict[str, Any]:
    """
    Extract the tool call from the state, execute the tool, and return the result to the state.
    """

    # Extracting information from LLM calls
    tool_call_data = state.tool_call

    if not tool_call_data:
        return {
             "messages": [ToolMessage(content="Error: No tool call data found.", tool_call_id="N/A")],
             "next": "respond_llm"
        }

    tool_id = tool_call_data.get("id", "unknown_id")
    tool_name = tool_call_data.get("function", {}).get("name")
    raw_args = tool_call_data.get("function", {}).get("arguments", "")

    if not tool_name:
        return {
             "messages": [ToolMessage(content="Error: Tool call format invalid.", tool_call_id=tool_id)],
             "next": "respond_llm"
        }

    tool_output = await tool_executor(tool_name, raw_args)

    # Wrap the results into a LangChain ToolMessage
    tool_message = ToolMessage(
        content=json.dumps(tool_output, ensure_ascii=False),
        tool_call_id=tool_id,
    )

    # Return to updated state: Attach tool output and redirect to LLM for further processing.
    return {
        "messages": [tool_message],
        "tool_call": None,
        "next": "respond_llm"
    }
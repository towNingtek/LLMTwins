import json
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, SystemMessage
from core.llm_clients import stream_ollama
from langchain_core.callbacks.manager import adispatch_custom_event

async def respond_llm_node(state: 'CatState', config: RunnableConfig) -> Dict[str, Any]:
    """
    Main LLM response node.
    This node produces the actual answer and determines whether a tool is needed.
    """

    # Prepaet to message
    # Check SystemMessage
    has_system_msg = any(isinstance(m, SystemMessage) for m in state.messages)

    if has_system_msg:
        # If SystemMessage already exists, use state.messages directly.
        raw_messages = state.messages
    else:
        # Otherwise, add system_prompt to profile.yaml.
        system_msg = SystemMessage(content=state.system_prompt)
        raw_messages = [system_msg] + state.messages

    final_text = ""
    tool_call_data = None

    # Collect LLM output
    async for line in stream_ollama(
        messages=raw_messages,
        model=state.model,
        tools=state.tools
    ):
        try:
            obj = json.loads(line)

            msg_dict = obj.get("message", {})
            choice_delta = obj.get("choices", [{}])[0].get("delta", {})

            # -------------------------------------------------
            # 1. Check tool calls - supports both plural and singular.
            # -------------------------------------------------
            t_calls = obj.get("tool_calls") or obj.get("tool_call")

            if not t_calls:
                t_calls = msg_dict.get("tool_calls") or msg_dict.get("tool_call")

            if not t_calls:
                t_calls = choice_delta.get("tool_calls") or choice_delta.get("tool_call")

            if t_calls:
                if isinstance(t_calls, list) and len(t_calls) > 0:
                    tool_call_data = t_calls[0]
                else:
                    tool_call_data = t_calls

                break

            # -------------------------------------------------
            # 2. Inspect and stream the content.
            # -------------------------------------------------
            content = msg_dict.get("content") or choice_delta.get("content")

            if content:
                final_text += content

                await adispatch_custom_event(
                    "store_token",
                    {"chunk": content},
                    config=config
                )

        except Exception:
            continue

    # -------------------------------------------------
    # 3. Return status update (Node ends)
    # -------------------------------------------------
    if tool_call_data:

        # Convert OpenAI toangChain ToolCall format
        # OpenAI: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
        # LangChain: {"name": "...", "args": {...}, "id": "...", "type": "tool_call"}
        function_data = tool_call_data.get("function", {})
        tool_name = function_data.get("name", "")
        raw_args = function_data.get("arguments", "")

        try:
            args_dict = json.loads(raw_args) if raw_args else {}
        except:
            args_dict = {}

        langchain_tool_call = {
            "name": tool_name,
            "args": args_dict,
            "id": tool_call_data.get("id", "unknown"),
            "type": "tool_call"
        }

        return {
            "messages": [AIMessage(content=final_text, tool_calls=[langchain_tool_call])],
            "tool_call": tool_call_data,
            "next": "call_tool"
        }
    else:
        return {
            "messages": [AIMessage(content=final_text)],
            "tool_call": None,
            "next": "end"
        }
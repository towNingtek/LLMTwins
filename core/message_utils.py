"""Message utility functions for LangChain message conversion."""

from typing import Any, Dict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)


def dict_to_base_message(message_dict: Dict[str, Any]) -> BaseMessage:
    """Dict to LangChain BaseMessage object"""
    role = message_dict.get("role")
    content = message_dict.get("content", "")

    # Instantiate the correct LangChain message class based on the role type
    if role == "system":
        return SystemMessage(content=content)
    elif role == "user":
        return HumanMessage(content=content)
    elif role == "assistant":
        return AIMessage(content=content)
    # If the role is unknown, default to HumanMessage to avoid interrupting the process
    else:
        return HumanMessage(content=content)

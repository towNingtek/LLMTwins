# roles/ai_cat/state.py
import yaml
import os
from typing import List, Dict, Any, Optional, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class CatState(BaseModel):
    # Load from profile.yaml
    name: str = "ai_cat"
    model: str = "openai/gpt-4o-mini"
    system_prompt: str = ""
    temperature: float = 0.3
    tools: list = Field(default_factory=list)

    messages: Annotated[List[BaseMessage], add_messages] = Field(default_factory=list)

    tool_call: Optional[Any] = None

    # Node streaming payload
    respond: Optional[Dict[str, Any]] = None

    # LangGraph need 'next' key
    next: Optional[str] = None

    # final output
    output: Optional[str] = None

    @classmethod
    def load_profile(cls, messages: Optional[List[BaseMessage]] = None):
        profile_path = os.path.join(os.path.dirname(__file__), "profile.yaml")

        with open(profile_path, "r", encoding="utf-8") as f:
            p = yaml.safe_load(f)

        # Ensure that the message type is also in the BaseMessage list in load_profile
        return cls(
            name=p.get("name", "ai_cat"),
            model=p.get("model", "openai/gpt-4o-mini"),
            system_prompt=p.get("system_prompt", ""),
            temperature=p.get("temperature", 0.3),
            tools=p.get("tools", []),
            messages=messages or []
        )
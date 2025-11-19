# roles/ai_cat/state.py
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import yaml
import os

class CatState(BaseModel):
    # 從 profile.yaml 載入
    name: str = "ai_cat"
    model: str = "openai/gpt-4o-mini"
    system_prompt: str = ""
    temperature: float = 0.3
    tools: list = Field(default_factory=list)

    # 對話資料
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    # Node streaming payload
    respond: Optional[Dict[str, Any]] = None

    # 最終輸出
    output: Optional[str] = None

    @classmethod
    def load_profile(cls, messages=None):
        profile_path = os.path.join(os.path.dirname(__file__), "profile.yaml")

        with open(profile_path, "r", encoding="utf-8") as f:
            p = yaml.safe_load(f)

        return cls(
            name=p.get("name", "ai_cat"),
            model=p.get("model", "openai/gpt-4o-mini"),
            system_prompt=p.get("system_prompt", ""),
            temperature=p.get("temperature", 0.3),
            tools=p.get("tools", []),
            messages=messages or []
        )
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import yaml
import os

class CatState(BaseModel):
    # === 來自 profile.yaml ===
    name: str = "ai_cat"
    model: str = "openai/gpt-4o-mini"
    system_prompt: str = "你是一隻可愛的 AI 貓咪喵～"
    temperature: float = 0.3
    output_style: Dict[str, Any] = Field(default_factory=dict)

    # === 對話資料 ===
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    # Node 最終產出
    output: Optional[str] = None

    # Node streaming payload
    respond: Optional[Dict[str, Any]] = None

    # === 自動載入 profile.yaml ===
    @classmethod
    def load_profile(cls):
        profile_path = os.path.join(os.path.dirname(__file__), "profile.yaml")
        if not os.path.exists(profile_path):
            return cls()  # fallback
        
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = yaml.safe_load(f)

        return cls(
            name            = profile.get("name", "ai_cat"),
            model           = profile.get("model", "openai/gpt-4o-mini"),
            system_prompt   = profile.get("system_prompt", "你是一個盡責的 AI 助理"),
            temperature     = profile.get("temperature", 0.3),
            output_style    = profile.get("output_style", {}),
            messages        = []
        )
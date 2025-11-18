# roles/ai_cat/state.py
from typing import List, Dict, Any
from pydantic import BaseModel

class CatState(BaseModel):
    model: str = "openai/gpt-4o-mini"
    messages: List[Dict[str, Any]] = []
    output: str | None = None

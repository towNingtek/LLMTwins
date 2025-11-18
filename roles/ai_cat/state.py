# roles/ai_cat/state.py
from pydantic import BaseModel

class CatState(BaseModel):
    message: str = ""
    mood: str = ""
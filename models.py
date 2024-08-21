from  pydantic import BaseModel
from typing import Optional, List

class prompt(BaseModel):
    role: str
    type: str
    format: Optional[str] = None
    model: Optional[str] = None
    injection: list = []
    tools: list = []
    message: str
from  pydantic import BaseModel
from typing import Optional, List

class regUser(BaseModel):
    name: str
    description: str

class getUser(BaseModel):
    name: str

class prompt(BaseModel):
    role: str
    type: str
    format: Optional[str] = None
    model: Optional[str] = None
    injection: list = []
    message: str

class callback_api(BaseModel):
    role: str
    message: str
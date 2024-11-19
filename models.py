from  pydantic import BaseModel
from typing import Optional
import json

class prompt(BaseModel):
    role: str
    message: str
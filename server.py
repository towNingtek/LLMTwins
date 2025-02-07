from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
from contextvars import ContextVar
import os

# Load environment variables
load_dotenv()

app = FastAPI()

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 創建一個上下文變數來存儲當前請求
current_request = ContextVar('current_request', default=None)

# Store loaded agents
loaded_agents = {}

class Prompt(BaseModel):
    role: str
    message: str
    params: Optional[Dict[str, Any]] = {}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/prompt")
async def handle_prompt(prompt: Prompt):
    try:
        # 將請求存儲在上下文中
        token = current_request.set(prompt)
        
        try:
            # 獲取對應的 agent
            if prompt.role not in loaded_agents:
                agent_path = f"agents/{prompt.role}"
                if not os.path.exists(agent_path):
                    raise HTTPException(status_code=404, detail=f"Agent not found: {prompt.role}")
                
                # 載入 agent
                from utils.module_handler import load_agents_from_directory
                agent = load_agents_from_directory(agent_path)
                if not agent:
                    raise HTTPException(status_code=404, detail=f"Failed to load agent: {prompt.role}")
                
                loaded_agents[prompt.role] = agent

            # 使用對應的 agent 處理請求
            agent = loaded_agents[prompt.role]
            response = agent.run(prompt.message, stream=False)
            
            # 處理回應
            content = None
            for message in response.messages:
                if message.role == "assistant" and message.content:
                    content = message.content
                    break
            
            if content is None:
                raise HTTPException(status_code=500, detail="No response from agent")

            needs_html = prompt.params.get("format") == "html" if prompt.params else False
            if needs_html:
                from utils.format import format_html
                content = format_html(content.strip())
                
            return {
                "result": True,
                "message": content
            }
            
        finally:
            # 清理上下文
            current_request.reset(token)
            
    except Exception as e:
        return {
            "result": False,
            "message": f"<div>處理過程發生錯誤：{str(e)}</div>"
        }
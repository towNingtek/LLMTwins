# app/main.py
import importlib
import pkgutil
import pathlib
import json
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="LLMTwins Workflow Server")

# =========================================
# 掃描 roles/ 自動載入 workflow fn
# =========================================
ROLES_PATH = pathlib.Path(__file__).resolve().parents[1] / "roles"
WORKFLOWS: Dict[str, Any] = {}

for module in pkgutil.iter_modules([str(ROLES_PATH)]):
    role_name = module.name
    try:
        module_path = f"roles.{role_name}.graph"
        graph_module = importlib.import_module(module_path)

        fn_name = f"{role_name}_workflow"
        workflow_fn = getattr(graph_module, fn_name, None)

        if workflow_fn:
            WORKFLOWS[role_name] = workflow_fn
            print(f"[LLMTwins] Loaded role workflow: {role_name}")
        else:
            print(f"[LLMTwins] No workflow factory found for role: {role_name}")

    except Exception as e:
        print(f"[LLMTwins] Failed to load role {role_name}: {e}")


# =========================================
# Models
# =========================================
class ChatRequest(BaseModel):
    role: str            # 例如 ai_cat
    input: Dict[str, Any]  # workflow astep() 的初始 state


# =========================================
# Helpers
# =========================================

def to_ndjson(obj: dict) -> str:
    """把 dict 序列化成一行 NDJSON（尾端自動加 \\n）"""
    return json.dumps(obj, ensure_ascii=False) + "\n"


# =========================================
# NDJSON Streaming wrapper
# =========================================

async def unified_stream(role: str, workflow_input: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    使用 astream_events 轉換 LangGraph event → NDJSON stream，實現 token 串流。
    """
    print("[DEBUG] unified_stream START (astream_events)")

    if role not in WORKFLOWS:
        raise HTTPException(status_code=404, detail=f"Unknown role: {role}")

    workflow_factory = WORKFLOWS[role]
    workflow = workflow_factory()

    try:
        # *** 核心關鍵：使用 astream_events 監聽所有事件 ***
        # version="v1" 適用於 LangGraph 1.0.3
        async for event in workflow.astream_events(workflow_input, version="v1", tags=[role]):
            kind = event["event"]
            
            # 1. 串流 Token 捕獲：監聽 'on_chain_stream' 事件
            if kind == "on_chain_stream":
                data = event.get("data", {})
                
                # 'chunk' 結構就是 Node 內部 yield 的內容: {"respond": {"token": "..."}}
                chunk = data.get("chunk")
                
                if isinstance(chunk, dict) and "respond" in chunk:
                    token_payload = chunk["respond"]
                    if isinstance(token_payload, dict) and "token" in token_payload:
                        token_content = token_payload["token"]
                        
                        # 找到 token，立刻輸出為 NDJSON
                        if token_content:
                            yield to_ndjson({
                                "type": "message",
                                "content": token_content
                            })
                            continue
            
            # 2. 結束事件：當整個流程結束時發出
            elif kind == "on_end":
                # 流程結束，發送完成信號
                yield to_ndjson({"type": "done"})
                print("[DEBUG] unified_stream END")
                return # 結束函數

    except Exception as e:
        err = f"[Workflow ERROR] {str(e)}"
        print(err)
        yield to_ndjson({"type": "error", "detail": err})

# =========================================
# Routes
# =========================================

@app.get("/")
def root():
    return {"message": "LLMTwins Workflow Server Ready (NDJSON stream enabled)"}


@app.get("/routes")
def list_routes():
    return [
        {
            "path": r.path,
            "methods": list(r.methods),
            "name": r.name,
        }
        for r in app.routes
    ]


@app.post("/chat")
async def chat_endpoint(body: ChatRequest):
    """
    通用 workflow 入口：
      - body.role 決定 workflow
      - body.input 作為 workflow 初始 state
      - 回傳 NDJSON 串流
    """
    role = body.role
    workflow_input = body.input

    if role not in WORKFLOWS:
        raise HTTPException(status_code=404, detail=f"Unknown role: {role}")

    return StreamingResponse(
        unified_stream(role, workflow_input),
        media_type="application/x-ndjson",
    )

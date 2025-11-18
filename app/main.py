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


def extract_text_from_event(event: Any) -> str:
    """從 workflow event 結構中抽 token（若存在）"""
    if isinstance(event, dict):
        if "respond" in event:
            payload = event["respond"]
            if isinstance(payload, dict) and "token" in payload:
                return payload["token"]
    return ""


# =========================================
# NDJSON Streaming wrapper
# =========================================

async def unified_stream(role: str, workflow_input: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    轉換 LangGraph astream(...) → NDJSON stream。
    """
    print("[DEBUG] unified_stream START")

    if role not in WORKFLOWS:
        raise HTTPException(status_code=404, detail=f"Unknown role: {role}")

    workflow_factory = WORKFLOWS[role]
    workflow = workflow_factory()

    try:
        async for event in workflow.astream(workflow_input):
            print("[DEBUG] event:", event)

            # 1) 若是 token event → 輸出 {"type":"message","content":"..."}
            text = extract_text_from_event(event)
            if text:
                yield to_ndjson({
                    "type": "message",
                    "content": text
                })
                continue

            # 2) 若不是 token event → 完整輸出整個 event（debug friendly）
            yield to_ndjson({
                "type": "event",
                "data": event
            })

        # workflow 結束
        yield to_ndjson({"type": "done"})
        print("[DEBUG] unified_stream END")

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

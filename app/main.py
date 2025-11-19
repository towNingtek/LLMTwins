# app/main.py
import importlib
import pkgutil
import pathlib
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from core.streaming_adapter import unified_stream

load_dotenv()

app = FastAPI(title="LLMTwins Workflow Server")

# ============================================================
# 自動載入 roles/ 所有 workflow + tools + executor
# ============================================================
ROLES_PATH = pathlib.Path(__file__).resolve().parents[1] / "roles"

WORKFLOWS: Dict[str, Any] = {}            # role → workflow function
ROLE_TOOL_EXECUTORS: Dict[str, Any] = {}  # role → tool_executor
ROLE_TOOLS: Dict[str, list] = {}          # role → tools schema list


for module in pkgutil.iter_modules([str(ROLES_PATH)]):
    role_name = module.name
    try:
        # -----------------------------
        # 載入 workflow：roles/{role}/graph.py
        # -----------------------------
        graph_module = importlib.import_module(f"roles.{role_name}.graph")
        fn_name = f"{role_name}_workflow"
        workflow_fn = getattr(graph_module, fn_name, None)

        if workflow_fn:
            WORKFLOWS[role_name] = workflow_fn
            print(f"[LLMTwins] Loaded workflow for: {role_name}")
        else:
            print(f"[LLMTwins] No workflow for: {role_name}")

        # -----------------------------
        # 載 tools：roles/{role}/tools.py
        # -----------------------------
        tools_schema = []
        executor_fn = None

        try:
            tool_module = importlib.import_module(f"roles.{role_name}.tools")

            # 工具 schema
            tools_schema = getattr(tool_module, "TOOLS", [])

            # executor
            executor_fn = getattr(tool_module, "tool_executor", None)

        except Exception as e:
            print(f"[LLMTwins] Tools load error for {role_name}: {e}")

        # 記錄工具 schema（即使是空 list 也要記）
        ROLE_TOOLS[role_name] = tools_schema
        print(f"[LLMTwins] Loaded tools ({len(tools_schema)}) for: {role_name}")

        # 記錄 executor
        if executor_fn:
            ROLE_TOOL_EXECUTORS[role_name] = executor_fn
            print(f"[LLMTwins] Loaded executor for: {role_name}")
        else:
            print(f"[LLMTwins] No executor for: {role_name}")

    except Exception as e:
        print(f"[LLMTwins] Failed to load role {role_name}: {e}")



# ============================================================
# Request Model
# ============================================================
class ChatRequest(BaseModel):
    role: str
    input: Dict[str, Any]


# ============================================================
# Routes
# ============================================================
@app.get("/")
def root():
    return {"message": "LLMTwins Workflow Server Ready (NDJSON stream)"}


@app.post("/chat")
async def chat_endpoint(body: ChatRequest):
    role = body.role

    if role not in WORKFLOWS:
        raise HTTPException(404, f"Unknown role: {role}")

    workflow_fn = WORKFLOWS[role]
    # Execute the role's workflow 'factory function' to get the actual workflow instance
    workflow = workflow_fn()
    initial_state = body.input

    # tools + executor
    role_tools = ROLE_TOOLS.get(role, [])
    executor = ROLE_TOOL_EXECUTORS.get(role)

    if executor is None:
        raise HTTPException(500, f"No tool executor for role: {role}")

    return StreamingResponse(
        unified_stream(
            model=initial_state["model"],
            messages=initial_state["messages"],
            tools=role_tools,
            tool_executor=executor,
        ),
        media_type="application/x-ndjson",
    )

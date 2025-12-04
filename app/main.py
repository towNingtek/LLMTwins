import pathlib
from typing import Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from core.message_utils import dict_to_base_message
from core.role_loader import load_all_roles
from core.streaming import stream_langgraph_workflow

load_dotenv()

app = FastAPI(title="LLMTwins Workflow Server")

# ============================================================
# Automatically load roles/all workflows + tools + executor
# ============================================================
ROLES_PATH = pathlib.Path(__file__).resolve().parents[1] / "roles"
WORKFLOWS, ROLE_TOOL_EXECUTORS, ROLE_TOOLS = load_all_roles(ROLES_PATH)

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
    # LangGraph instance (compiled)
    workflow = workflow_fn()

    # Transform input messages + Injection tool definition
    initial_input_data = body.input

    # Ensure messages exist and convert each dictionary into a LangChain BaseMessage object
    if 'messages' in initial_input_data and isinstance(initial_input_data['messages'], list):
        # Transform using list comprehensions
        initial_input_data['messages'] = [
            dict_to_base_message(m)
            for m in initial_input_data['messages']
        ]

    # If the client does not provide tools, then use ROLE_TOOLS.
    if 'tools' not in initial_input_data or not initial_input_data['tools']:
        initial_input_data['tools'] = ROLE_TOOLS.get(role, [])

    initial_state = initial_input_data

    return StreamingResponse(
        # Calling LangGraph stream processor
        stream_langgraph_workflow(
            workflow=workflow,
            initial_state=initial_state,
        ),
        media_type="application/x-ndjson",
    )
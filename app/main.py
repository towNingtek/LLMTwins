import importlib
import pkgutil
from fastapi import FastAPI
from langserve import add_routes
import pathlib

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="LLMTwins Workflow Server")

from app.routers.streaming import router as stream_router
app.include_router(stream_router)

# --- 自動掃描 roles 資料夾 ---
ROLES_PATH = pathlib.Path(__file__).resolve().parents[1] / "roles"

for module in pkgutil.iter_modules([str(ROLES_PATH)]):
    role_name = module.name
    try:
        # 動態導入每個 role 的 graph.py
        module_path = f"roles.{role_name}.graph"
        graph_module = importlib.import_module(module_path)

        # workflow 需命名為 "{role_name}_workflow"
        attr_name = f"{role_name}_workflow"
        workflow_fn = getattr(graph_module, attr_name, None)

        if workflow_fn:
            print(f"[LLMTwins] Loaded role: {role_name}")
            add_routes(app, workflow_fn(), path=f"/workflow/{role_name}")

    except Exception as e:
        print(f"[LLMTwins] Failed to load role {role_name}: {e}")

@app.get("/")
def root():
    return {"message": "LLMTwins Workflow Server Ready ver-0.1"}


@app.get("/routes")
def list_routes():
    return [
        {
            "path": r.path,
            "methods": list(r.methods),
            "name": r.name
        }
        for r in app.routes
    ]
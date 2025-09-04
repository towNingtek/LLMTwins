# server.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.logger import logger

from app.state_store import ConversationStateStore
from app.core.config import load_settings
from app.core.policy import load_deny_guard

# Routers
from app.routers.sessions import router as sessions_router
from app.routers.debug import router as debug_router
from app.routers.admin import router as admin_router
from app.routers.chat import router as chat_router
from app.routers.pipeline import router as pipeline_router
from app.routers import chat_demo

# ============================================================================
# Configuration & Initialization
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

settings = load_settings(BASE_DIR)

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
app.state.settings = load_settings(BASE_DIR)

from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    "https://nsdgs.4impact.cc",   # 前端正式站
    "https://eva.4impact.cc",     # 你 configs 也有
    "http://localhost:3000",      # 本機開發 (React)
    "http://localhost:5173",      # 本機開發 (Vite)
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,     # 不用 "*"，一些反代和預檢轉址時會掉 header
    allow_credentials=False,           # 你目前沒用 cookie，維持 False
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,
)


# 掛上 routers
app.include_router(sessions_router)
app.include_router(debug_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(pipeline_router)
app.include_router(chat_demo.router)

# ============================================================================
# Startup: inject shared state & load policy
# ============================================================================

@app.on_event("startup")
async def on_startup():
    app.state.state_store = ConversationStateStore(settings.sess_base)
    app.state.base_dir = BASE_DIR
    app.state.sess_base = settings.sess_base
    app.state.ollama_base_url = settings.ollama_base_url
    app.state.denylist_path = settings.denylist_path
    app.state.deny_enabled = settings.deny_enabled

    guard, summary, err = load_deny_guard(app.state.denylist_path)
    app.state.deny_guard = guard
    prefix = (
        f"[policy] loaded {app.state.denylist_path}: {summary}"
        if guard else f"[policy] load failed: {err}"
    )
    logger.info(f"{prefix} | enabled={app.state.deny_enabled}")


# ============================================================================
# Health Check & Root
# ============================================================================

@app.get("/")
@app.head("/")
async def root_ok():
    return Response(status_code=204)

@app.get("/health")
async def health():
    return {"result": "Healthy Server!"}
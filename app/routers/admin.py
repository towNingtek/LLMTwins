# app/routers/admin.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/policy/reload")
async def admin_policy_reload(request: Request):
    try:
        dg = request.app.state.deny_guard
        path = request.app.state.denylist_path
        # 動態載入，避免循環依賴
        from policy.guard import DenyGuard
        request.app.state.deny_guard = DenyGuard.load_from_path(path)
        return {"ok": True, "summary": request.app.state.deny_guard.summary()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

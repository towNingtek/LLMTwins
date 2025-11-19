# core/tool_api.py

from typing import Callable, Dict, Any

def get_executor_for_role(
    role: str,
    role_registry: Dict[str, Callable]
) -> Callable[[str, str | None], Any]:
    """
    提供 role 專屬的 tool_executor，不讓 core 直接 import roles/。

    role_registry: 由 app/main.py 掃描 roles/*/tools.py 得到
                   { "ai_cat": tool_executor, ... }
    """

    if role in role_registry:
        return role_registry[role]

    # 若該角色完全沒有工具 → 給一個 fallback executor
    async def unknown_tool_executor(name: str, raw_args: str | None):
        return {"error": f"Role '{role}' has no tools. Tool '{name}' cannot be executed."}

    return unknown_tool_executor

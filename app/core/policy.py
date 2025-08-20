# app/core/policy.py
from typing import Optional, Tuple, Any
from policy.guard import DenyGuard

def load_deny_guard(path: str) -> Tuple[Optional[DenyGuard], Optional[Any], Optional[str]]:
    """
    回傳 (guard, summary, error)。成功時 error=None。
    """
    try:
        guard = DenyGuard.load_from_path(path)
        return guard, guard.summary(), None
    except Exception as e:
        return None, None, str(e)

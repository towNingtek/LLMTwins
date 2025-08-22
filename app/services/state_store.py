# app/services/state_store.py
from typing import Any, Dict
from pathlib import Path
from app.services.state_utils import read_state as _read_state, write_state as _write_state

def read_state(sess_base: Path, session_id: str) -> Dict[str, Any]:
    """安全包裝：讀不到回 {}。"""
    try:
        st = _read_state(sess_base, session_id)
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}

def write_state(sess_base: Path, session_id: str, state: Dict[str, Any]) -> None:
    """安全包裝：確保輸入是 dict。"""
    _write_state(sess_base, session_id, dict(state or {}))

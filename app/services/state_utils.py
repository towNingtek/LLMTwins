from pathlib import Path
import json
from datetime import datetime, timezone

def session_dir(sess_base: str, session_id: str) -> Path:
    return Path(sess_base) / session_id

def state_path(sess_base: str, session_id: str) -> Path:
    return session_dir(sess_base, session_id) / "state" / "conversation_state.json"

def read_state(sess_base: str, session_id: str) -> dict:
    p = state_path(sess_base, session_id)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

def write_state(sess_base: str, session_id: str, st: dict) -> None:
    p = state_path(sess_base, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    st["last_updated"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

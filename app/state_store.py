# app/state_store.py
#!/usr/bin/env python3
import json, os, enum
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ISO = lambda: datetime.now(timezone.utc).isoformat()

class Mode(str, enum.Enum):
    SESSION_ONLY = "session_only"
    DOC_ALIGNED  = "doc_aligned"

class Step(str, enum.Enum):
    IDLE            = "idle"
    PARSED          = "parsed"
    PREFILL_DONE    = "prefill_done"
    ASKING          = "asking"
    READY_TO_COMMIT = "ready_to_commit"
    COMMITTED       = "committed"

@dataclass
class ConvState:
    mode: Mode = Mode.SESSION_ONLY
    step: Step = Step.IDLE
    asked: List[str] = None
    pending: List[str] = None
    current_field: Optional[str] = None
    doc: Optional[Dict[str, Any]] = None
    cms: Optional[Dict[str, Any]] = None
    last_updated: str = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["step"] = self.step.value
        d["asked"] = self.asked or []
        d["pending"] = self.pending or []
        d["last_updated"] = self.last_updated or ISO()
        return d

class ConversationStateStore:
    """
    File-based state store for sessions/<sid>/state/conversation_state.json
    - 原子寫入：先寫 .tmp，再 os.replace()
    - 無外部相依
    """
    def __init__(self, sess_base: Path):
        self.sess_base = Path(sess_base)

    # ---------- low-level ----------
    def _state_path(self, sid: str) -> Path:
        return self.sess_base / sid / "state" / "conversation_state.json"

    def _ensure_parent(self, p: Path):
        p.parent.mkdir(parents=True, exist_ok=True)

    def _read(self, sid: str) -> Dict[str, Any]:
        fp = self._state_path(sid)
        if not fp.exists():
            return {}
        with fp.open("r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}

    def _write_atomic(self, sid: str, data: Dict[str, Any]):
        fp = self._state_path(sid)
        self._ensure_parent(fp)
        tmp = fp.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, fp)

    # ---------- public APIs ----------
    def init_session(self, sid: str):
        st = ConvState()
        st.last_updated = ISO()
        self._write_atomic(sid, st.to_dict())
        return st.to_dict()

    def mark_parsed(self, sid: str, filename: str, pages: int, pending_fields: List[str]):
        st = self._read(sid) or {}
        st.update({
            "mode": Mode.DOC_ALIGNED.value,
            "step": Step.PARSED.value,
            "doc": {"filename": filename, "pages": int(pages)},
            "pending": pending_fields,
            "last_updated": ISO(),
        })
        self._write_atomic(sid, st)
        return st

    def apply_prefill(self, sid: str, suggestions: Dict[str, Dict[str, Any]], pending_fields: List[str]):
        st = self._read(sid) or {}
        st.update({
            "mode": Mode.DOC_ALIGNED.value,
            "step": Step.PREFILL_DONE.value,
            "suggestions": suggestions,        # {field: {value, confidence, ...}}
            "pending": pending_fields,
            "last_updated": ISO(),
        })
        self._write_atomic(sid, st)
        return st

    def start_asking(self, sid: str, field: str):
        st = self._read(sid) or {}
        asked = st.get("asked") or []
        if field not in (st.get("pending") or []):
            # no-op if not pending
            pass
        st.update({
            "step": Step.ASKING.value,
            "current_field": field,
            "asked": asked,
            "last_updated": ISO(),
        })
        self._write_atomic(sid, st)
        return st

    def record_answer(self, sid: str, field: str, still_pending: List[str]):
        st = self._read(sid) or {}
        asked = st.get("asked") or []
        if field not in asked:
            asked.append(field)
        st.update({
            "asked": asked,
            "pending": still_pending,
            "current_field": None,
            "last_updated": ISO(),
        })
        # auto-advance to READY_TO_COMMIT if無待問
        if not still_pending:
            st["step"] = Step.READY_TO_COMMIT.value
        self._write_atomic(sid, st)
        return st

    def ready_to_commit(self, sid: str):
        st = self._read(sid) or {}
        st.update({
            "step": Step.READY_TO_COMMIT.value,
            "last_updated": ISO(),
        })
        self._write_atomic(sid, st)
        return st

    def mark_committed(self, sid: str, uuid: str):
        st = self._read(sid) or {}
        st.update({
            "step": Step.COMMITTED.value,
            "cms": {"uuid": uuid, "committed_at": ISO()},
            "last_updated": ISO(),
        })
        self._write_atomic(sid, st)
        return st

    def get(self, sid: str) -> Dict[str, Any]:
        return self._read(sid) or {}


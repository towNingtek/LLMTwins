# app/services/mapping_service.py
import json
from pathlib import Path
from datetime import datetime

def init_mapping_draft(session_id: str, sess_base: Path) -> Path:
    session_dir = Path(sess_base) / session_id
    parsed_path = session_dir / "artifacts" / "parsed.json"
    out_path = session_dir / "mapping_draft.json"

    if out_path.exists():
        return out_path  # 已存在就不要覆寫

    doc = {
        "model": "Project",
        "session_id": session_id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": {
            "parsed_path": str(parsed_path),
            "strategy": "llm_only_prefill_v0.1"
        },
        "data": {}
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    return out_path

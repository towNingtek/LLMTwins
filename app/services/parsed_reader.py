# app/services/parsed_reader.py
from pathlib import Path
from app.services.parsed_text import extract_plaintext as _extract_plaintext

def extract_plaintext(sess_base: Path, session_id: str, max_chars: int = 3000) -> str:
    """
    安全包裝 parsed.json → 純文字；限定最大長度，例外時回空字串。
    """
    try:
        base = Path(sess_base)
        plain = _extract_plaintext(base, session_id, max_chars=max_chars)
        return (plain or "")[:max_chars]
    except Exception:
        return ""

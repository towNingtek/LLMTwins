# app/core/config.py
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

@dataclass
class Settings:
    base_dir: Path
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://140.127.196.91:8082"))
    ollama_auth: Optional[str] = field(default_factory=lambda: os.getenv("OLLAMA_AUTH"))
    denylist_path: str = field(default_factory=lambda: os.getenv("DENYLIST_JSON", "policy/deny.json"))
    deny_enabled: bool = field(default_factory=lambda: os.getenv("DENY_ENABLED", "true").lower() in ("1", "true", "yes"))
    sess_base: Path = field(default_factory=lambda: Path(os.getenv("SESS_BASE", "sessions")))
    allowed_origins: List[str] = field(default_factory=lambda: [
        "https://eva.4impact.cc",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://nsdgs.4impact.cc",
    ])

def load_settings(base_dir: Path) -> Settings:
    s = Settings(base_dir=base_dir)
    s.sess_base.mkdir(parents=True, exist_ok=True)
    return s

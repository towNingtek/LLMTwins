# app/session_utils.py

import time
import json
import yaml
from copy import deepcopy
from pathlib import Path


def session_dir(session_id: str, sess_base: Path) -> Path:
    return sess_base / session_id


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def append_history(session_id: str, role: str, content: str, sess_base: Path):
    """Append one line NDJSON to chat_history.jsonl"""
    if not content:
        return
    d = session_dir(session_id, sess_base)
    ensure_dir(d)
    fp = d / "chat_history.jsonl"
    rec = {"ts": time.time(), "role": role, "content": content}
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")


def deep_merge(a, b):
    """dict 深合併：b 覆蓋 a"""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return deepcopy(b)
    out = deepcopy(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def write_effective_template(session_id: str, base_dir: Path, sess_base: Path, model: str = "project") -> dict:
    """
    建立 session 的 effective_conversation_template.yaml（套用 overrides）
    """
    sdir = session_dir(session_id, sess_base)
    ensure_dir(sdir / "config")

    base_tpl = base_dir / f"configs/conversation_templates/{model}.yaml"
    eff_path = sdir / "config" / "effective_conversation_template.yaml"
    overrides_path = sdir / "config" / "template_overrides.yaml"

    if not base_tpl.exists():
        return {"ok": False, "reason": f"missing global template: {base_tpl}"}

    with base_tpl.open("r", encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f) or {}

    if overrides_path.exists():
        with overrides_path.open("r", encoding="utf-8") as f:
            overrides = yaml.safe_load(f) or {}
        eff_cfg = deep_merge(base_cfg, overrides)
    else:
        eff_cfg = base_cfg

    with eff_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(eff_cfg, f, allow_unicode=True, sort_keys=False)

    return {"ok": True, "effective": str(eff_path)}


def init_session_dirs(session_id: str, sess_base: Path):
    """初始化必要資料夾結構"""
    d = session_dir(session_id, sess_base)
    ensure_dir(d / "raw")
    ensure_dir(d / "config")
    ensure_dir(d / "state")
    ensure_dir(d / "artifacts")


import json
import yaml
from pathlib import Path

ROLES_DIR = Path(__file__).resolve().parents[1] / "roles"


def load_role_profile(role_name: str) -> dict:
    """
    統一載入角色設定：
    - roles/{role_name}/profile.yaml
    - roles/{role_name}/profile.json

    缺少則用預設角色設定。
    """

    role_path = ROLES_DIR / role_name

    yaml_path = role_path / "profile.yaml"
    json_path = role_path / "profile.json"

    if yaml_path.exists():
        return yaml.safe_load(yaml_path.read_text())

    if json_path.exists():
        return json.loads(json_path.read_text())

    # 預設 profile
    return {
        "system_prompt": "你是一個友善的中文 AI 助理。",
        "model": "openai/gpt-4o-mini",
        "temperature": 0.5
    }
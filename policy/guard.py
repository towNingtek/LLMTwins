# policy/guard.py
from __future__ import annotations
import json, os, re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

@dataclass
class Category:
    id: str
    name: str
    type: str               # 目前只支援 "regex"
    rules: List[str]
    pattern: Optional[re.Pattern] = None

@dataclass
class DenyGuard:
    version: str
    refusal_text: str
    categories: List[Category] = field(default_factory=list)
    union_pattern: Optional[re.Pattern] = None  # 全部規則的聯集，加速掃描

    @classmethod
    def load_from_path(cls, path: str) -> "DenyGuard":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        version = data.get("version", "unknown")
        refusal_text = data.get("refusal_text", "抱歉，我無法回覆這個問題。")
        cats: List[Category] = []

        for c in data.get("categories", []):
            cat = Category(
                id=c.get("id"), name=c.get("name"),
                type=c.get("type", "regex"),
                rules=list(c.get("rules", []))
            )
            if cat.type != "regex":
                raise ValueError(f"unsupported rule type: {cat.type} (category {cat.id})")
            # 編譯每個類別自己的 pattern（忽略大小寫）
            if cat.rules:
                cat.pattern = re.compile("|".join(cat.rules), re.I)
            cats.append(cat)

        # 聯集 pattern（加速：先粗篩，再找類別）
        all_rules = [r for c in cats for r in c.rules]
        union_pattern = re.compile("|".join(all_rules), re.I) if all_rules else None

        return cls(version=version, refusal_text=refusal_text,
                   categories=cats, union_pattern=union_pattern)

    def test_text(self, text: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        回傳：(是否命中, 類別ID, 命中的片段)
        先用 union 粗篩，再細判逐類別。
        """
        if not text:
            return (False, None, None)
        if self.union_pattern and not self.union_pattern.search(text):
            return (False, None, None)
        for c in self.categories:
            if c.pattern:
                m = c.pattern.search(text)
                if m:
                    return (True, c.id, m.group(0))
        return (False, None, None)

    def summary(self) -> Dict:
        return {
            "version": self.version,
            "categories": [
                {"id": c.id, "name": c.name, "rule_count": len(c.rules)}
                for c in self.categories
            ],
            "total_rules": sum(len(c.rules) for c in self.categories),
            "has_union": bool(self.union_pattern),
        }


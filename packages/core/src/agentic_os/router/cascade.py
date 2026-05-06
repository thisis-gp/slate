from __future__ import annotations
from pydantic import BaseModel

TASK_TYPE_TIERS: dict[str, str] = {
    "drafting": "free",
    "search": "free",
    "summarization": "free",
    "requirements": "free",
    "documentation": "free",
    "implementation": "cheap",
    "coding": "cheap",
    "testing": "cheap",
    "debugging": "cheap",
    "integration": "cheap",
    "review": "premium",
    "architecture": "premium",
    "security": "premium",
    "orchestration": "premium",
    "council": "premium",
}


class TierConfig(BaseModel):
    provider: str
    model: str


class CascadeRouter:
    def __init__(self, tiers: dict[str, TierConfig]):
        self._tiers = tiers

    def select_tier(self, task_type: str) -> str:
        return TASK_TYPE_TIERS.get(task_type.lower(), "cheap")

    def get_tier_config(self, task_type: str) -> TierConfig:
        tier = self.select_tier(task_type)
        return self._tiers[tier]

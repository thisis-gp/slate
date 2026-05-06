from __future__ import annotations
from enum import Enum
from typing import Protocol, runtime_checkable, AsyncIterator
from pydantic import BaseModel, computed_field


class ModelTier(str, Enum):
    FREE = "free"
    CHEAP = "cheap"
    PREMIUM = "premium"


class Message(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str
    cache_control: dict | None = None  # {"type": "ephemeral"} for prompt caching


class LLMResponse(BaseModel):
    content: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cost_usd: float
    model: str

    @computed_field
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse: ...

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]: ...

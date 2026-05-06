from __future__ import annotations
import anthropic
from .base import Message, LLMResponse

PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}


class AnthropicProvider:
    """Direct Anthropic SDK — used for CTO orchestrator only.
    Enables cache_control on system prompt for 90% cost reduction."""

    def __init__(self, api_key: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    def _price(self, model: str, input_t: int, output_t: int, cache_read_t: int) -> float:
        key = model.split("/")[-1] if "/" in model else model
        in_rate, out_rate = PRICING.get(key, (15.0, 75.0))
        cache_read_rate = in_rate * 0.1
        return (input_t * in_rate + output_t * out_rate + cache_read_t * cache_read_rate) / 1_000_000

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        system_blocks = []
        chat_messages = []

        for msg in messages:
            if msg.role == "system":
                block: dict = {"type": "text", "text": msg.content}
                if msg.cache_control:
                    block["cache_control"] = msg.cache_control
                system_blocks.append(block)
            else:
                chat_messages.append({"role": msg.role, "content": msg.content})

        model_id = model.split("/")[-1] if "/" in model else model

        kwargs: dict = {
            "model": model_id,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system_blocks:
            kwargs["system"] = system_blocks

        response = await self._client.messages.create(**kwargs)
        usage = response.usage
        content = response.content[0].text
        return LLMResponse(
            content=content,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
            cost_usd=self._price(
                model_id, usage.input_tokens, usage.output_tokens,
                getattr(usage, "cache_read_input_tokens", 0)
            ),
            model=model_id,
        )

    async def stream(self, messages, *, model, max_tokens=4096):
        raise NotImplementedError("Streaming added in Phase 4")

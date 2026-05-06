from __future__ import annotations
import httpx
from .base import Message, LLMResponse

PRICING: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-r1": (0.55, 2.19),
    "qwen/qwen3-coder-480b:free": (0.0, 0.0),
    "google/gemini-2.5-flash": (0.15, 0.60),
    "anthropic/claude-haiku-4-5-20251001": (0.80, 4.00),
    "deepseek/deepseek-r1:free": (0.0, 0.0),
    "default": (1.0, 3.0),
}


class OpenRouterProvider:
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _price(self, model: str, input_tokens: int, output_tokens: int) -> float:
        in_rate, out_rate = PRICING.get(model, PRICING["default"])
        return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "HTTP-Referer": "https://github.com/agentic-os",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=self._price(model, input_tokens, output_tokens),
            model=model,
        )

    async def stream(self, messages, *, model, max_tokens=4096):
        raise NotImplementedError("Streaming added in Phase 4")

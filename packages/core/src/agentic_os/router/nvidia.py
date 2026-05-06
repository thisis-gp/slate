from __future__ import annotations
import httpx
from .base import Message, LLMResponse

FREE_MODELS = {
    "meta/llama-3.3-70b-instruct",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "qwen/qwen2.5-coder-32b-instruct",
}


class NVIDIANIMProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

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
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        usage = data.get("usage", {})
        content = data["choices"][0]["message"]["content"]
        cost = 0.0 if model in FREE_MODELS else 0.001
        return LLMResponse(
            content=content,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cost_usd=cost,
            model=model,
        )

    async def stream(self, messages, *, model, max_tokens=4096):
        raise NotImplementedError("Streaming added in Phase 4")

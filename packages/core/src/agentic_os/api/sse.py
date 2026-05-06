import asyncio
import json
from typing import AsyncIterator

async def event_stream(queue: asyncio.Queue) -> AsyncIterator[str]:
    """Yield SSE-formatted strings from a queue. Yields keepalive every 15s."""
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=15.0)
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"

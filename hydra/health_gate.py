from __future__ import annotations

import asyncio
from time import monotonic

import httpx


async def wait_for_health(
    url: str,
    *,
    timeout_seconds: float = 60.0,
    interval_seconds: float = 0.25,
) -> bool:
    deadline = monotonic() + timeout_seconds
    async with httpx.AsyncClient(timeout=2.0) as client:
        while monotonic() < deadline:
            try:
                response = await client.get(url)
                if response.status_code < 500:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(interval_seconds)
    return False

from __future__ import annotations

import json
from time import perf_counter

import httpx

from hydra.runtime.benchmark_protocol import StreamMetrics


async def benchmark_chat_stream(
    url: str,
    *,
    model: str,
    prompt: str,
    max_tokens: int = 128,
) -> tuple[StreamMetrics, str]:
    metrics = StreamMetrics.start()
    pieces: list[str] = []
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
    }
    metrics.started_at = perf_counter()
    async with (
        httpx.AsyncClient(timeout=120.0) as client,
        client.stream("POST", url, json=payload) as response,
    ):
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            event = json.loads(data)
            choices = event.get("choices", [])
            if not choices:
                continue
            token = choices[0].get("delta", {}).get("content")
            if token:
                metrics.token()
                pieces.append(token)
    metrics.finish()
    return metrics, "".join(pieces)

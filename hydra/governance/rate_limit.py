# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Small in-process sliding-window limiter for the API gateway."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, requests: int, window_seconds: float = 60.0) -> None:
        if requests <= 0:
            return
        now = monotonic()
        cutoff = now - window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="HYDRA rate limit exceeded",
                )
            hits.append(now)

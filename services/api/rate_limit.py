"""Small per-user rate limiter for expensive asynchronous jobs."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from .security import current_user_id


class UserRateLimiter:
    def __init__(self, limit: int = 20, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, user_id: str) -> None:
        now = time.monotonic()
        events = self._events[user_id]
        while events and now - events[0] >= self.window_seconds:
            events.popleft()
        if len(events) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many expensive requests; try again shortly")
        events.append(now)


expensive_limiter = UserRateLimiter()


async def expensive_rate_limit(user_id: str = Depends(current_user_id)) -> str:
    expensive_limiter.check(user_id)
    return user_id

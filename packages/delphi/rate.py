"""Process-local outbound request limiter. No file state."""
from __future__ import annotations
import threading
import time
from collections import deque
RATE_LIMIT = 30
RATE_WINDOW_SECONDS = 60.0
class RateLimiter:
    def __init__(self, limit=RATE_LIMIT, window=RATE_WINDOW_SECONDS, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._lock = threading.Lock()
        self._hits = deque()
    def reserve(self, count):
        if type(count) is not int or count < 0 or count > self.limit:
            return False
        if count == 0:
            return True
        with self._lock:
            now = self.clock()
            cutoff = now - self.window
            while self._hits and self._hits[0] <= cutoff:
                self._hits.popleft()
            if len(self._hits) + count > self.limit:
                return False
            self._hits.extend([now] * count)
            return True
LIMITER = RateLimiter()
def reserve(count):
    return LIMITER.reserve(count)

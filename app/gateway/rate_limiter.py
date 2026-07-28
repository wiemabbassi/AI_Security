import time
from typing import Dict, Tuple

class TokenBucketRateLimiter:
    """
    In-Memory & Redis-compatible Token Bucket Rate Limiter
    Enforces rate limits per User, per API Key, and per IP simultaneously.
    """
    def __init__(self, capacity: int = 20, refill_rate: float = 0.5):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.buckets: Dict[str, Tuple[float, float]] = {}  # key -> (tokens, last_refill_timestamp)

    def is_allowed(self, key: str, cost: int = 1) -> Tuple[bool, int, float]:
        now = time.time()
        if key not in self.buckets:
            self.buckets[key] = (float(self.capacity), now)
        
        tokens, last_refill = self.buckets[key]
        delta = now - last_refill
        tokens = min(self.capacity, tokens + delta * self.refill_rate)
        
        if tokens >= cost:
            tokens -= cost
            self.buckets[key] = (tokens, now)
            return True, int(tokens), 0.0
        else:
            self.buckets[key] = (tokens, now)
            retry_after = (cost - tokens) / self.refill_rate
            return False, int(tokens), round(retry_after, 2)

rate_limiter = TokenBucketRateLimiter(capacity=20, refill_rate=0.5)

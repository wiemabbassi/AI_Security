import time
from typing import Dict, Tuple, Optional
from app.config import settings

try:
    import redis
except ImportError:
    redis = None

class TokenBucketRateLimiter:
    """
    Redis-Backed & In-Memory Fallback Token Bucket Rate Limiter.
    Enforces simultaneous rate limits across User ID, API Key, and IP Address.
    """
    def __init__(self, capacity: int = 20, refill_rate: float = 0.5):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.buckets: Dict[str, Tuple[float, float]] = {}  # key -> (tokens, last_refill_timestamp)
        self.redis_client = None

        if redis is not None:
            try:
                self.redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=0,
                    socket_connect_timeout=0.5
                )
                self.redis_client.ping()
            except Exception:
                self.redis_client = None

    def _check_single_bucket(self, key: str, cost: int = 1) -> Tuple[bool, int, float]:
        now = time.time()
        
        # 1. Try Redis distributed token bucket if connected
        if self.redis_client is not None:
            try:
                pipe = self.redis_client.pipeline()
                tokens_key = f"ratelimit:{key}:tokens"
                last_key = f"ratelimit:{key}:last"

                raw_tokens = self.redis_client.get(tokens_key)
                raw_last = self.redis_client.get(last_key)

                tokens = float(raw_tokens) if raw_tokens else float(self.capacity)
                last_refill = float(raw_last) if raw_last else now

                delta = now - last_refill
                tokens = min(self.capacity, tokens + delta * self.refill_rate)

                if tokens >= cost:
                    tokens -= cost
                    pipe.set(tokens_key, tokens)
                    pipe.set(last_key, now)
                    pipe.execute()
                    return True, int(tokens), 0.0
                else:
                    retry_after = (cost - tokens) / self.refill_rate
                    return False, int(tokens), round(retry_after, 2)
            except Exception:
                pass  # Fall back to in-memory

        # 2. In-memory token bucket fallback
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

    def is_allowed(self, key: str, user_id: Optional[str] = None, api_key: Optional[str] = None, client_ip: Optional[str] = None, cost: int = 1) -> Tuple[bool, int, float]:
        # Enforce rate limiting per-User, per-API Key, AND per-IP simultaneously
        keys_to_check = []
        if user_id:
            keys_to_check.append(f"user:{user_id}")
        if api_key:
            keys_to_check.append(f"apikey:{api_key}")
        if client_ip:
            keys_to_check.append(f"ip:{client_ip}")
        if not keys_to_check:
            keys_to_check.append(key)

        min_remaining = self.capacity
        max_retry_after = 0.0

        for k in keys_to_check:
            allowed, remaining, retry_after = self._check_single_bucket(k, cost)
            min_remaining = min(min_remaining, remaining)
            if not allowed:
                max_retry_after = max(max_retry_after, retry_after)

        if max_retry_after > 0.0:
            return False, min_remaining, max_retry_after

        return True, min_remaining, 0.0

rate_limiter = TokenBucketRateLimiter(capacity=settings.RATE_LIMIT_MAX_REQUESTS, refill_rate=0.5)


"""
Rate Limiter for WebSocket Gateway
Token bucket algorithm with Redis backend
"""

import time
from typing import Optional

import redis.asyncio as redis

from app.config import settings


class RateLimiter:
    """Token bucket rate limiter with Redis backend"""
    
    def __init__(self, redis_client: redis.Redis, config: settings):
        self.redis = redis_client
        self.config = config
        self.prefix = config.rate_limit.redis_prefix
    
    async def check_limit(
        self,
        key: str,
        rate: float,
        burst: int,
    ) -> bool:
        """
        Check if request is within rate limit
        
        Args:
            key: Rate limit key (e.g., "crdt:user123")
            rate: Requests per second
            burst: Maximum burst size
            
        Returns:
            True if allowed, False if rate limited
        """
        if not self.config.rate_limit.enabled:
            return True
        
        redis_key = f"{self.prefix}{key}"
        now = time.time()
        
        # Lua script for atomic token bucket
        lua_script = """
        local key = KEYS[1]
        local rate = tonumber(ARGV[1])
        local burst = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local requested = tonumber(ARGV[4])
        
        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket[1])
        local last_refill = tonumber(bucket[2])
        
        if not tokens then
            tokens = burst
            last_refill = now
        end
        
        -- Refill tokens
        local elapsed = now - last_refill
        local new_tokens = math.min(burst, tokens + elapsed * rate)
        
        if new_tokens >= requested then
            new_tokens = new_tokens - requested
            redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 60)
            return {1, new_tokens}
        else
            redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 60)
            return {0, new_tokens}
        end
        """
        
        script = self.redis.register_script(lua_script)
        result = await script(
            keys=[f"{self.prefix}{key}"],
            args=[rate, burst, time.time(), 1]
        )
        
        allowed = result[0] == 1
        return allowed
    
    async def get_current_usage(self, key: str) -> dict:
        """Get current rate limit usage"""
        redis_key = f"{self.prefix}{key}"
        data = await self.redis.hmget(redis_key, 'tokens', 'last_refill')
        tokens = float(data[0]) if data[0] else 0
        last_refill = float(data[1]) if data[1] else 0
        return {
            "tokens": tokens,
            "last_refill": last_refill,
        }
    
    async def reset_limit(self, key: str) -> bool:
        """Reset rate limit for a key"""
        redis_key = f"{self.prefix}{key}"
        result = await self.redis.delete(redis_key)
        return result > 0


class SlidingWindowRateLimiter:
    """Sliding window rate limiter for more precise limiting"""
    
    def __init__(self, redis_client: redis.Redis, config: settings):
        self.redis = redis_client
        self.config = config
        self.prefix = f"{config.rate_limit.redis_prefix}sw:"
    
    async def check_limit(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> bool:
        """
        Check sliding window rate limit
        
        Args:
            key: Rate limit key
            limit: Maximum requests in window
            window: Time window in seconds
        """
        if not self.config.rate_limit.enabled:
            return True
        
        redis_key = f"{self.prefix}{key}"
        now = time.time()
        window_start = now - window
        
        # Add current request
        await self.redis.zadd(redis_key, {str(now): now})
        
        # Remove old entries
        await self.redis.zremrangebyscore(redis_key, 0, window_start)
        
        # Count current requests
        count = await self.redis.zcard(redis_key)
        
        # Set expiry
        await self.redis.expire(redis_key, window + 1)
        
        return count <= limit
    
    async def get_current_count(self, key: str, window: int) -> int:
        """Get current request count in window"""
        redis_key = f"{self.prefix}{key}"
        now = time.time()
        window_start = now - window
        
        await self.redis.zremrangebyscore(redis_key, 0, window_start)
        return await self.redis.zcard(redis_key)
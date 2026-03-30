"""Simple rate limiter for API endpoints"""
import time
from typing import Dict
from functools import wraps
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}
    
    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        
        # Clean old requests
        if client_id in self.requests:
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id]
                if now - req_time < self.window_seconds
            ]
        else:
            self.requests[client_id] = []
        
        # Check if under limit
        if len(self.requests[client_id]) < self.max_requests:
            self.requests[client_id].append(now)
            return True
        
        return False
    
    def get_remaining(self, client_id: str) -> int:
        if client_id not in self.requests:
            return self.max_requests
        
        now = time.time()
        recent_requests = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.window_seconds
        ]
        
        return max(0, self.max_requests - len(recent_requests))

# Global rate limiters
api_limiter = RateLimiter(max_requests=30, window_seconds=60)  # 30 requests/minute
heavy_limiter = RateLimiter(max_requests=10, window_seconds=60)  # 10 requests/minute for heavy endpoints

def rate_limit(max_requests: int = 30, window_seconds: int = 60):
    """Rate limiting decorator"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Try to get client IP from request
            client_id = "unknown"
            for arg in args:
                if hasattr(arg, 'client'):
                    client_id = arg.client.host
                    break
            
            limiter = RateLimiter(max_requests, window_seconds)
            if not limiter.is_allowed(client_id):
                remaining = limiter.get_remaining(client_id)
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "message": f"Too many requests. Maximum {max_requests} per {window_seconds} seconds.",
                        "remaining": remaining,
                        "retry_after": window_seconds
                    }
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Cache for expensive operations
endpoint_cache = {}

def cache_response(cache_key: str, ttl_seconds: int = 30):
    """Cache endpoint responses"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            now = time.time()
            
            # Check cache
            if cache_key in endpoint_cache:
                cached_data, timestamp = endpoint_cache[cache_key]
                if now - timestamp < ttl_seconds:
                    return cached_data
            
            # Execute and cache
            result = await func(*args, **kwargs)
            endpoint_cache[cache_key] = (result, now)
            
            # Clean old cache entries
            old_keys = [
                key for key, (_, timestamp) in endpoint_cache.items()
                if now - timestamp > ttl_seconds * 2
            ]
            for key in old_keys:
                del endpoint_cache[key]
            
            return result
        return wrapper
    return decorator

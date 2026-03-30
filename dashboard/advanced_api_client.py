"""Advanced API client with async I/O, connection pooling, and optimized parsing"""
import asyncio
import httpx
import orjson
import time
from typing import Dict, Any, Optional, List
from functools import wraps
import streamlit as st
from tenacity import retry, stop_after_attempt, wait_exponential

class AdvancedAPIClient:
    """High-performance API client with async I/O and connection pooling"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self._client = None
        self._session_cache = {}
        self._request_timestamps = {}
        
    async def _get_client(self):
        """Get or create HTTP client with connection pooling"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                timeout=httpx.Timeout(10.0, connect=5.0, read=30.0),
                http2=True,  # Enable HTTP/2 for multiplexing
            )
        return self._client
    
    def _get_cache_key(self, endpoint: str, method: str, data: Any = None) -> str:
        """Generate cache key for request"""
        if data:
            # Use orjson for fast serialization
            data_str = orjson.dumps(data, default=str).decode()
            return f"{method}:{endpoint}:{data_str}"
        return f"{method}:{endpoint}"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def _make_request(self, method: str, endpoint: str, data: Any = None) -> Optional[Dict]:
        """Make HTTP request with retries and exponential backoff"""
        client = await self._get_client()
        url = endpoint if endpoint.startswith('/') else f'/{endpoint}'
        
        try:
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json=data)
            elif method == "DELETE":
                response = await client.delete(url)
            else:
                return None
            
            if response.status_code == 200:
                # Use orjson for fast parsing
                return orjson.loads(response.content)
            elif response.status_code == 429:
                # Rate limited - the retry decorator will handle this
                raise httpx.HTTPStatusError("Rate limited", request=response.request, response=response)
            else:
                return None
                
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            # Log error but don't raise - let retry decorator handle it
            print(f"Request error: {e}")
            raise
    
    async def request(self, endpoint: str, method: str = "GET", data: Any = None, 
                     cache_ttl: int = 30, use_cache: bool = True) -> Optional[Dict]:
        """Make API request with caching and async I/O"""
        cache_key = self._get_cache_key(endpoint, method, data)
        
        # Check cache first
        if use_cache and cache_ttl > 0:
            cached = self._get_from_cache(cache_key, cache_ttl)
            if cached is not None:
                return cached
        
        # Make request
        try:
            result = await self._make_request(method, endpoint, data)
            
            # Cache successful results
            if result is not None and use_cache and cache_ttl > 0:
                self._set_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            print(f"API request failed: {e}")
            return None
    
    def _get_from_cache(self, key: str, ttl: int) -> Optional[Dict]:
        """Get data from cache with TTL"""
        if key in self._session_cache:
            data, timestamp = self._session_cache[key]
            if time.time() - timestamp < ttl:
                return data
            else:
                del self._session_cache[key]
        return None
    
    def _set_cache(self, key: str, data: Dict):
        """Set data in cache with timestamp"""
        self._session_cache[key] = (data, time.time())
        
        # Clean old entries (keep cache size manageable)
        if len(self._session_cache) > 100:
            oldest_key = min(
                self._session_cache.keys(),
                key=lambda k: self._session_cache[k][1]
            )
            del self._session_cache[oldest_key]
    
    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def clear_cache(self, pattern: str = None):
        """Clear cache entries"""
        if pattern:
            keys_to_remove = [k for k in self._session_cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self._session_cache[key]
        else:
            self._session_cache.clear()

# Global async client
_async_client = None

def get_async_client():
    """Get or create global async client"""
    global _async_client
    if _async_client is None:
        _async_client = AdvancedAPIClient()
    return _async_client

def async_api_request(endpoint: str, method: str = "GET", data: Any = None, 
                      cache_ttl: int = 30, use_cache: bool = True) -> Optional[Dict]:
    """Synchronous wrapper for async API requests"""
    client = get_async_client()
    
    # Run async function in event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running (Streamlit), create new one
            import nest_asyncio
            nest_asyncio.apply()
        
        return asyncio.run(client.request(endpoint, method, data, cache_ttl, use_cache))
    except Exception as e:
        print(f"Async request failed: {e}")
        return None

async def batch_requests(requests: List[tuple]) -> List[Optional[Dict]]:
    """Make multiple API requests concurrently"""
    client = get_async_client()
    
    # Create tasks for all requests
    tasks = []
    for endpoint, method, data, ttl in requests:
        task = client.request(endpoint, method, data, ttl or 30)
        tasks.append(task)
    
    # Execute all requests concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Clean up
    await client.close()
    
    return results

def batch_api_requests(requests: List[tuple]) -> List[Optional[Dict]]:
    """Synchronous wrapper for batch requests"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        
        return asyncio.run(batch_requests(requests))
    except Exception as e:
        print(f"Batch requests failed: {e}")
        return [None] * len(requests)

# Decorator for caching function results
def cache_function(ttl_seconds: int = 300):
    """Decorator for caching function results"""
    def decorator(func):
        cache = {}
        timestamps = {}
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and args
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Check cache
            if cache_key in cache:
                data, timestamp = cache[cache_key]
                if time.time() - timestamp < ttl_seconds:
                    return data
                else:
                    del cache[cache_key]
                    del timestamps[cache_key]
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            cache[cache_key] = (result, time.time())
            timestamps[cache_key] = time.time()
            
            # Clean old entries
            if len(cache) > 50:
                oldest_key = min(timestamps.keys(), key=lambda k: timestamps[k])
                del cache[oldest_key]
                del timestamps[oldest_key]
            
            return result
        
        return wrapper
    return decorator

# Example usage for dashboard optimization
@cache_function(ttl_seconds=60)
def get_system_stats():
    """Get system stats with caching"""
    return async_api_request("/stats", cache_ttl=60)

@cache_function(ttl_seconds=30)
def get_pending_downloads():
    """Get pending downloads with caching"""
    return async_api_request("/videos/pending-download?limit=100", cache_ttl=30)

@cache_function(ttl_seconds=30)
def get_pending_posts():
    """Get pending posts with caching"""
    return async_api_request("/videos/pending-post?limit=100", cache_ttl=30)

def load_dashboard_data_concurrent():
    """Load all dashboard data concurrently"""
    requests = [
        ("/health", "GET", None, 30),
        ("/stats", "GET", None, 60),
        ("/videos/pending-download?limit=100", "GET", None, 30),
        ("/videos/pending-post?limit=100", "GET", None, 30),
        ("/scheduler/next-post", "GET", None, 30),
        ("/tasks/status", "GET", None, 30),
    ]
    
    results = batch_api_requests(requests)
    
    return {
        'health': results[0],
        'stats': results[1],
        'pending_downloads': results[2],
        'pending_posts': results[3],
        'next_post': results[4],
        'task_status': results[5],
    }

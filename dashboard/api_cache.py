"""API request caching for dashboard to reduce rate limiting"""
import time
from typing import Dict, Any, Optional
import streamlit as st

class DashboardAPICache:
    """Simple cache for dashboard API requests"""
    def __init__(self, default_ttl: int = 30):
        self.default_ttl = default_ttl
        # Initialize cache if not exists
        if 'api_cache' not in st.session_state:
            st.session_state.api_cache = {}
        if 'api_cache_timestamps' not in st.session_state:
            st.session_state.api_cache_timestamps = {}
    
    def get(self, cache_key: str, ttl: Optional[int] = None) -> Optional[Any]:
        """Get cached data"""
        cache = st.session_state.api_cache
        timestamps = st.session_state.api_cache_timestamps
        ttl = ttl or self.default_ttl
        
        if cache_key in cache:
            if time.time() - timestamps[cache_key] < ttl:
                return cache[cache_key]
            else:
                # Expired, remove it
                del cache[cache_key]
                del timestamps[cache_key]
        
        return None
    
    def set(self, cache_key: str, data: Any):
        """Set cached data"""
        st.session_state.api_cache[cache_key] = data
        st.session_state.api_cache_timestamps[cache_key] = time.time()
    
    def clear(self, pattern: Optional[str] = None):
        """Clear cache entries"""
        if pattern:
            keys_to_remove = [k for k in st.session_state.api_cache.keys() if pattern in k]
            for key in keys_to_remove:
                del st.session_state.api_cache[key]
                if key in st.session_state.api_cache_timestamps:
                    del st.session_state.api_cache_timestamps[key]
        else:
            st.session_state.api_cache.clear()
            st.session_state.api_cache_timestamps.clear()

# Global cache instance
dashboard_cache = DashboardAPICache()

def cached_api_request(endpoint: str, method: str = "GET", data: dict = None, ttl: int = 30):
    """Make API request with caching"""
    cache_key = f"{method}:{endpoint}:{str(data) if data else ''}"
    
    # Try cache first
    cached_result = dashboard_cache.get(cache_key, ttl)
    if cached_result is not None:
        return cached_result
    
    # Make actual request
    try:
        import requests
        url = f"http://localhost:8000{endpoint}"
        
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=30)
        elif method == "DELETE":
            response = requests.delete(url, timeout=10)
        else:
            return None
        
        if response.status_code == 200:
            result = response.json()
            # Cache successful responses
            dashboard_cache.set(cache_key, result)
            return result
        elif response.status_code == 429:
            # Rate limited, wait and retry once
            import time
            time.sleep(1)
            if method == "GET":
                response = requests.get(url, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                dashboard_cache.set(cache_key, result)
                return result
        
        return None
    except:
        return None

def invalidate_cache(endpoint_pattern: str = None):
    """Invalidate cache for specific endpoints"""
    if endpoint_pattern:
        dashboard_cache.clear(endpoint_pattern)
    else:
        dashboard_cache.clear()

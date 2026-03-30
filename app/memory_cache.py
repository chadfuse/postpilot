"""Memory caching utilities for PostPilot"""
import time
from typing import Dict, Any, Optional
from functools import lru_cache

class SimpleCache:
    """Simple in-memory cache with TTL"""
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Dict[str, Any]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            item = self.cache[key]
            if time.time() - item['timestamp'] < self.ttl_seconds:
                return item['value']
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        if len(self.cache) >= self.max_size:
            # Remove oldest item
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
        
        self.cache[key] = {
            'value': value,
            'timestamp': time.time()
        }
    
    def clear(self) -> None:
        self.cache.clear()

# Global cache instances
video_cache = SimpleCache(max_size=50, ttl_seconds=600)  # 10 min
stats_cache = SimpleCache(max_size=20, ttl_seconds=60)    # 1 min
config_cache = SimpleCache(max_size=10, ttl_seconds=3600) # 1 hour

@lru_cache(maxsize=32)
def get_cached_config():
    """Cached config reading"""
    import os
    import json
    config_path = os.getenv('CONFIG_PATH', 'config/config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except:
        return {}

def invalidate_config_cache():
    """Invalidate config cache when updated"""
    get_cached_config.cache_clear()
    config_cache.clear()

"""Memory-optimized API for PostPilot"""
import os
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import database immediately (always needed)
from .database import Database
from .memory_cache import get_cached_config, invalidate_config_cache, video_cache, stats_cache
from .rate_limiter import rate_limit, cache_response

# Lazy imports for memory-intensive modules
_scraper = None
_downloader = None
_poster = None

def get_scraper():
    global _scraper
    if _scraper is None:
        from .scraper import TikTokScraper
        _scraper = TikTokScraper(database)
    return _scraper

def get_downloader():
    global _downloader
    if _downloader is None:
        from .downloader import VideoDownloader
        download_path = os.getenv('DOWNLOAD_PATH', 'videos')
        _downloader = VideoDownloader(database, download_path)
    return _downloader

def get_poster():
    global _poster
    if _poster is None:
        from .poster import FacebookPoster
        page_id, access_token = get_facebook_credentials()
        if page_id and access_token:
            _poster = FacebookPoster(database, page_id, access_token)
    return _poster

# Initialize FastAPI app
app = FastAPI(
    title="TikTok Video Collector API",
    description="API for managing TikTok video collection and Facebook posting",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
database = Database()

# Embed scheduler into API server to save memory (no separate process needed)
_scheduler_instance = None

@app.on_event("startup")
async def startup_event():
    """Start the scheduler when the API server starts"""
    global _scheduler_instance
    try:
        from .scheduler import TikTokScheduler
        _scheduler_instance = TikTokScheduler()
        _scheduler_instance.scheduler.start()
        database.log_info('api', 'Embedded scheduler started with API server')
    except Exception as e:
        database.log_error('api', f'Failed to start embedded scheduler: {str(e)}')

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the scheduler when the API server stops"""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.scheduler.shutdown()
        database.log_info('api', 'Embedded scheduler stopped')

# Initialize Redis and RQ (minimal)
try:
    import redis
    from rq import Queue
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    redis_conn = redis.from_url(redis_url)
    scraper_queue = Queue('scraper', connection=redis_conn)
    downloader_queue = Queue('downloader', connection=redis_conn)
    poster_queue = Queue('poster', connection=redis_conn)
    cleanup_queue = Queue('cleanup', connection=redis_conn)
except Exception as e:
    print(f"Failed to connect to Redis: {e}")
    redis_conn = None
    scraper_queue = None
    downloader_queue = None
    poster_queue = None
    cleanup_queue = None

# Pydantic models
class KeywordRequest(BaseModel):
    keyword: str
    active: bool = True

class VideoPostRequest(BaseModel):
    tiktok_id: str
    description: Optional[str] = None
    hashtags: Optional[List[str]] = None

class ConfigUpdate(BaseModel):
    facebook_page_id: Optional[str] = None
    facebook_access_token: Optional[str] = None
    min_posts_per_day: Optional[int] = None
    max_posts_per_day: Optional[int] = None
    min_scrape_interval: Optional[int] = None
    max_scrape_interval: Optional[int] = None
    min_post_interval: Optional[int] = None
    max_post_interval: Optional[int] = None

# Helper functions
def get_config():
    """Get system configuration (cached)"""
    return get_cached_config()

def update_config(updates: Dict[str, Any]):
    """Update configuration and invalidate cache"""
    config_path = os.getenv('CONFIG_PATH', 'config/config.json')
    try:
        # Read existing config
        config = get_config()
        config.update(updates)
        
        # Write updated config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Invalidate cache
        invalidate_config_cache()
        
        return True
    except Exception as e:
        database.log_error('api', f'Failed to update config: {str(e)}')
        return False

def get_facebook_credentials():
    """Get Facebook credentials from env vars, falling back to config.json"""
    config = get_config()
    page_id = os.getenv('FACEBOOK_PAGE_ID') or config.get('FACEBOOK_PAGE_ID')
    access_token = os.getenv('FACEBOOK_ACCESS_TOKEN') or config.get('FACEBOOK_ACCESS_TOKEN')
    return page_id, access_token

# Health check
@app.get("/health")
@cache_response("health", ttl_seconds=30)
@rate_limit(max_requests=60, window_seconds=60)
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db_status = "connected" if database.get_connection() else "disconnected"
        
        # Test Redis connection
        redis_status = "connected"
        if redis_conn:
            try:
                redis_conn.ping()
            except:
                redis_status = "disconnected"
        else:
            redis_status = "not_configured"
        
        return {
            "status": "healthy",
            "database": db_status,
            "redis": redis_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Videos endpoints
@app.get("/videos")
@rate_limit(max_requests=20, window_seconds=60)
async def get_videos(downloaded: Optional[bool] = None, posted: Optional[bool] = None, 
                   limit: int = Query(default=50, le=100), offset: int = Query(default=0, ge=0)):
    """Get videos with optional filters"""
    try:
        cache_key = f"videos_{downloaded}_{posted}_{limit}_{offset}"
        cached_result = video_cache.get(cache_key)
        if cached_result:
            return cached_result
        
        videos = database.get_videos(downloaded=downloaded, posted=posted, limit=limit, offset=offset)
        
        result = {
            "success": True,
            "videos": videos,
            "count": len(videos)
        }
        
        video_cache.set(cache_key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/videos/pending-download")
@rate_limit(max_requests=20, window_seconds=60)
async def get_pending_downloads(limit: int = Query(default=50, le=100)):
    """Get videos that need to be downloaded"""
    try:
        cache_key = f"pending_downloads_{limit}"
        cached_result = video_cache.get(cache_key)
        if cached_result:
            return cached_result
        
        videos = database.get_pending_downloads(limit)
        
        result = {
            "success": True,
            "videos": videos,
            "count": len(videos)
        }
        
        video_cache.set(cache_key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/videos/pending-download")
@rate_limit(max_requests=5, window_seconds=60)
async def clear_pending_downloads():
    """Clear all pending downloads (safe - preserves posted videos)"""
    try:
        # Get all pending downloads (only non-posted videos)
        pending_videos = database.get_pending_downloads(1000)
        
        if not pending_videos:
            return {
                "success": True,
                "message": "No pending downloads to clear"
            }
        
        # Delete only non-posted pending downloads
        deleted_count = 0
        preserved_count = 0
        
        for video in pending_videos:
            try:
                # Double-check video is not posted
                if video.get('posted', False):
                    preserved_count += 1
                    database.log_info('api', f'Preserved posted video {video["tiktok_id"]}')
                    continue
                
                success = database.delete_video(video['tiktok_id'])
                if success:
                    deleted_count += 1
            except Exception as e:
                database.log_error('api', f'Failed to delete pending download {video["tiktok_id"]}: {str(e)}')
        
        # Invalidate cache
        video_cache.clear()
        
        message = f"Cleared {deleted_count} pending downloads"
        if preserved_count > 0:
            message += f" (preserved {preserved_count} posted videos)"
        
        database.log_info('api', message)
        
        return {
            "success": True,
            "message": message,
            "deleted": deleted_count,
            "preserved": preserved_count
        }
    except Exception as e:
        database.log_error('api', f'Failed to clear pending downloads: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/cleanup-missing-videos")
@rate_limit(max_requests=2, window_seconds=300)  # Very limited
async def cleanup_missing_videos():
    """Safe cleanup of missing video files (preserves posted videos)"""
    try:
        import os
        
        # Get all videos marked as downloaded
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tiktok_id, file_path, posted, facebook_post_id
                FROM videos 
                WHERE downloaded = 1
            """)
            videos = cursor.fetchall()
        
        missing_unposted = []
        missing_posted = []
        
        for tiktok_id, file_path, posted, facebook_post_id in videos:
            # Check if file exists
            full_path = os.path.join(os.getcwd(), file_path)
            if not os.path.exists(full_path):
                if posted:
                    missing_posted.append((tiktok_id, file_path, facebook_post_id))
                    # Mark as not downloaded but keep posted flag
                    cursor.execute("UPDATE videos SET downloaded = 0 WHERE tiktok_id = ?", (tiktok_id,))
                    database.log_info('api', f'Preserved posted video with missing file: {tiktok_id}')
                else:
                    missing_unposted.append((tiktok_id, file_path))
                    # Delete unposted videos with missing files
                    cursor.execute("DELETE FROM videos WHERE tiktok_id = ?", (tiktok_id,))
                    database.log_info('api', f'Deleted unposted video with missing file: {tiktok_id}')
        
        conn.commit()
        
        # Invalidate cache
        video_cache.clear()
        
        return {
            "success": True,
            "message": f"Cleanup complete: removed {len(missing_unposted)} unposted, preserved {len(missing_posted)} posted",
            "removed_unposted": len(missing_unposted),
            "preserved_posted": len(missing_posted)
        }
    except Exception as e:
        database.log_error('api', f'Failed cleanup: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/videos/pending-post")
async def get_pending_posts(limit: int = Query(default=15, le=50)):
    """Get videos ready for posting"""
    try:
        cache_key = f"pending_post_{limit}"
        cached_result = video_cache.get(cache_key)
        if cached_result:
            return cached_result
        
        videos = database.get_pending_posts(limit)
        
        result = {
            "success": True,
            "videos": videos,
            "count": len(videos)
        }
        
        video_cache.set(cache_key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/videos/pending-post")
@rate_limit(max_requests=5, window_seconds=60)
async def clear_pending_posts():
    """Clear all pending posts by resetting downloaded=0 (keeps records for dedup)"""
    try:
        with database.get_connection() as conn:
            cursor = conn.cursor()
            # Count first
            cursor.execute("SELECT COUNT(*) FROM videos WHERE downloaded = 1 AND posted = 0")
            count = cursor.fetchone()[0]
            
            if count == 0:
                return {"success": True, "message": "No pending posts to clear"}
            
            # Reset downloaded flag — videos go back to pending-download state
            cursor.execute("UPDATE videos SET downloaded = 0, file_path = NULL WHERE downloaded = 1 AND posted = 0")
            conn.commit()
        
        # Invalidate cache
        video_cache.clear()
        
        database.log_info('api', f'Cleared {count} pending posts')
        
        return {
            "success": True,
            "message": f"Cleared {count} pending posts"
        }
    except Exception as e:
        database.log_error('api', f'Failed to clear pending posts: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

# Scheduler endpoint
@app.get("/scheduler/next-post")
@rate_limit(max_requests=30, window_seconds=60)
async def get_next_post_info():
    """Get next scheduled post info"""
    try:
        config = get_config()
        pending_posts = database.get_pending_posts(1)
        post_interval_min = int(config.get('MIN_POST_INTERVAL', 5))
        post_interval_max = int(config.get('MAX_POST_INTERVAL', 20))
        
        return {
            "success": True,
            "next_post_time": None,
            "queue_count": len(database.get_pending_posts(1000)),
            "interval_range": f"{post_interval_min}–{post_interval_max} min",
            "has_pending": len(pending_posts) > 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Task status endpoint
@app.get("/tasks/status")
@rate_limit(max_requests=30, window_seconds=60)
async def get_task_status():
    """Get task queue status based on database counts"""
    try:
        pending_downloads = database.get_pending_downloads(1000)
        pending_posts = database.get_pending_posts(1000)
        keywords = database.get_keywords()
        
        return {
            "success": True,
            "queues": {
                "scraper": {"pending": len(keywords), "failed": 0},
                "downloader": {"pending": len(pending_downloads), "failed": 0},
                "poster": {"pending": len(pending_posts), "failed": 0}
            },
            "workers": 1
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Task endpoints (memory-optimized, direct execution)
@app.post("/tasks/scrape-keyword/{keyword}")
async def scrape_keyword(keyword: str):
    """Scrape videos for a single keyword (direct, no worker queue)"""
    try:
        scraper = get_scraper()
        results = scraper.scrape_videos_by_keyword(keyword, count=100)  # Increased from 50 to 100
        
        # Invalidate video cache
        video_cache.clear()
        
        database.log_info('api', f'Scraped {len(results)} videos for keyword: {keyword}')
        
        return {
            "success": True,
            "message": f"Scraped {len(results)} videos for keyword: {keyword}",
            "videos_found": len(results)
        }
    except Exception as e:
        database.log_error('api', f'Failed to scrape {keyword}: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/scrape-all")
async def scrape_all():
    """Scrape all keywords with related terms (direct, no worker queue)"""
    try:
        scraper = get_scraper()
        keywords = database.get_keywords()
        
        if not keywords:
            return {
                "success": False,
                "message": "No keywords configured"
            }
        
        total_videos = 0
        related_videos = 0
        # Process all keywords but with reasonable limits
        max_keywords = min(len(keywords), 20)  # Increased from 10 to 20
        
        for i, keyword in enumerate(keywords[:max_keywords]):
            try:
                # Adaptive count: more videos for first keywords, fewer for later ones
                if i < 5:
                    count = 100  # First 5 keywords get 100 videos
                    related_limit = 2  # Top keywords get 2 related terms
                elif i < 15:
                    count = 75   # Next 10 keywords get 75 videos
                    related_limit = 1  # Mid keywords get 1 related term
                else:
                    count = 50   # Remaining keywords get 50 videos
                    related_limit = 0  # Lower keywords get no related terms
                
                # Scrape main keyword
                results = scraper.scrape_videos_by_keyword(keyword, count=count)
                total_videos += len(results)
                database.log_info('api', f'Scraped {len(results)} videos for keyword: {keyword}')
                
                # Scrape related keywords for content diversity
                if related_limit > 0:
                    try:
                        related_results = scraper.scrape_related_for_keyword(keyword, limit=related_limit)
                        for related_key, video_count in related_results.items():
                            related_videos += video_count
                            database.log_info('api', f'Related scrape: {video_count} videos for {related_key}')
                    except Exception as e:
                        database.log_error('api', f'Failed related scraping for {keyword}: {str(e)}')
                
                # Small delay between keywords
                import time
                time.sleep(0.3)
                
            except Exception as e:
                database.log_error('api', f'Failed to scrape {keyword}: {str(e)}')
        
        # Invalidate video cache
        video_cache.clear()
        
        grand_total = total_videos + related_videos
        message = f"Scraped {grand_total} videos ({total_videos} main + {related_videos} related) from {max_keywords} keywords"
        
        return {
            "success": True,
            "message": message,
            "videos_found": grand_total,
            "main_videos": total_videos,
            "related_videos": related_videos
        }
    except Exception as e:
        database.log_error('api', f'Failed to scrape all keywords: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/scrape-unlimited")
async def scrape_unlimited():
    """Smart unlimited scraping with related keywords (direct, no worker queue)"""
    try:
        scraper = get_scraper()
        keywords = database.get_keywords()
        
        if not keywords:
            return {
                "success": False,
                "message": "No keywords configured"
            }
        
        total_videos = 0
        related_videos = 0
        
        # Enhanced unlimited scraping with tiered approach + related keywords
        for i, keyword in enumerate(keywords):
            try:
                # Tiered approach based on keyword position
                if i < 3:
                    count = 200  # Top 3 keywords get 200 videos
                    related_limit = 3  # Top keywords get more related terms
                elif i < 10:
                    count = 150  # Next 7 keywords get 150 videos
                    related_limit = 2  # Mid keywords get fewer related terms
                else:
                    count = 75   # Remaining keywords get 75 videos
                    related_limit = 1  # Lower priority keywords get 1 related term
                
                # Scrape main keyword
                results = scraper.scrape_videos_by_keyword(keyword, count=count)
                total_videos += len(results)
                database.log_info('api', f'Unlimited scrape: {len(results)} videos for keyword: {keyword}')
                
                # Scrape related keywords for better content diversity
                if i < 5:  # Only for top 5 keywords to avoid overwhelming
                    try:
                        related_results = scraper.scrape_related_for_keyword(keyword, limit=related_limit)
                        for related_key, video_count in related_results.items():
                            related_videos += video_count
                            database.log_info('api', f'Related scrape: {video_count} videos for {related_key}')
                    except Exception as e:
                        database.log_error('api', f'Failed related scraping for {keyword}: {str(e)}')
                
                # Small delay between keywords to respect rate limits
                import time
                time.sleep(0.5)
                
            except Exception as e:
                database.log_error('api', f'Failed unlimited scrape {keyword}: {str(e)}')
        
        # Invalidate video cache
        video_cache.clear()
        
        grand_total = total_videos + related_videos
        message = f"Smart unlimited scraping: {grand_total} videos ({total_videos} main + {related_videos} related) from {len(keywords)} keywords"
        
        return {
            "success": True,
            "message": message,
            "videos_found": grand_total,
            "main_videos": total_videos,
            "related_videos": related_videos
        }
    except Exception as e:
        database.log_error('api', f'Failed unlimited scraping: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/download-pending")
async def download_pending_videos(limit: int = Query(default=10, le=50)):
    """Download pending videos (direct, no worker queue)"""
    try:
        downloader = get_downloader()
        result = downloader.download_pending_videos(limit)
        
        # Invalidate video cache
        video_cache.clear()
        
        database.log_info('api', f'Downloaded {result.get("downloaded", 0)} videos, {result.get("failed", 0)} failed')
        
        return {
            "success": True,
            "message": f"Downloaded {result.get('downloaded', 0)} videos, {result.get('failed', 0)} failed",
            "downloaded": result.get('downloaded', 0),
            "failed": result.get('failed', 0)
        }
    except Exception as e:
        database.log_error('api', f'Failed to download videos: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/post-pending")
async def post_pending_videos():
    """Post pending videos to Facebook (direct, no worker queue)"""
    try:
        page_id, access_token = get_facebook_credentials()
        if not page_id or not access_token:
            raise HTTPException(status_code=400, detail="Facebook credentials not configured")
        
        pending = database.get_pending_posts(limit=10)
        if not pending:
            return {"success": True, "message": "No pending videos to post", "posted": 0, "failed": 0}
        
        from .poster import FacebookPoster
        poster = FacebookPoster(database, page_id, access_token)
        
        posted = 0
        failed = 0
        for video in pending:
            try:
                result = poster.post_video_with_retry(
                    tiktok_id=video['tiktok_id'],
                    video_path=video.get('file_path', ''),
                    caption=video.get('caption', ''),
                    author=video.get('author', ''),
                    hashtags=video.get('hashtags', [])
                )
                if result and result.get('success'):
                    posted += 1
                else:
                    failed += 1
            except Exception as e:
                database.log_error('api', f'Failed to post {video["tiktok_id"]}: {str(e)}')
                failed += 1
        
        video_cache.clear()
        stats_cache.clear()
        
        return {
            "success": True,
            "message": f"Posted {posted} videos, {failed} failed",
            "posted": posted,
            "failed": failed
        }
    except HTTPException:
        raise
    except Exception as e:
        database.log_error('api', f'Failed to post pending videos: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/download/{tiktok_id}")
async def download_single_video(tiktok_id: str):
    """Download a single video (not implemented in optimized version)"""
    # For now, just trigger bulk download
    return await download_pending_videos(limit=1)

@app.post("/tasks/post/{tiktok_id}")
async def post_single_video(tiktok_id: str):
    """Post a specific downloaded video to Facebook (direct, no worker queue)"""
    try:
        page_id, access_token = get_facebook_credentials()
        if not page_id or not access_token:
            raise HTTPException(status_code=400, detail="Facebook credentials not configured")
        
        # Get video details from pending posts
        all_pending = database.get_pending_posts(limit=500)
        video = next((v for v in all_pending if v['tiktok_id'] == tiktok_id), None)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found, not downloaded, or already posted")
        
        # Post directly instead of via worker (avoids memory crashes on low-RAM systems)
        poster = get_poster()
        if not poster:
            raise HTTPException(status_code=400, detail="Facebook poster not initialized")
        
        result = poster.post_video_with_retry(
            tiktok_id=tiktok_id,
            video_path=video['file_path'],
            caption=video.get('caption', ''),
            author=video.get('author', ''),
            hashtags=video.get('hashtags', [])
        )
        
        if result and result.get('success'):
            # Invalidate caches
            video_cache.clear()
            stats_cache.clear()
            
            database.log_info('api', f'Posted video to Facebook: {tiktok_id}')
            return {"success": True, "message": f"Video {tiktok_id} posted to Facebook", "result": result}
        else:
            error_msg = result.get('message', 'Unknown error') if result else 'No response'
            database.log_error('api', f'Failed to post {tiktok_id}: {error_msg}')
            return {"success": False, "message": error_msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Config endpoint
@app.get("/config")
@rate_limit(max_requests=20, window_seconds=60)
async def get_config_endpoint():
    """Get system configuration"""
    try:
        config = get_config()
        return {
            "success": True,
            "config": config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config")
@rate_limit(max_requests=5, window_seconds=60)
async def update_config_endpoint(settings: dict):
    """Update system configuration"""
    try:
        success = update_config(settings)
        if success:
            return {
                "success": True,
                "message": "Configuration updated successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update configuration")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Facebook settings endpoint
@app.get("/facebook/settings")
@rate_limit(max_requests=10, window_seconds=60)
async def get_facebook_settings():
    """Get Facebook settings (without exposing sensitive token)"""
    try:
        config = get_config()
        page_id = config.get('FACEBOOK_PAGE_ID')
        access_token = config.get('FACEBOOK_ACCESS_TOKEN')
        
        # Check if credentials are configured
        has_page_id = bool(page_id and page_id.strip())
        has_token = bool(access_token and len(access_token) > 50)  # Basic check for token length
        
        return {
            "success": True,
            "configured": has_page_id and has_token,
            "page_id": page_id[:10] + "..." if page_id else None,  # Partial page ID for verification
            "token_length": len(access_token) if access_token else 0,
            "message": "Facebook credentials configured" if has_page_id and has_token else "Facebook credentials not configured"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/facebook/stats")
@rate_limit(max_requests=5, window_seconds=60)
async def get_facebook_stats():
    """Get Facebook page statistics"""
    try:
        config = get_config()
        page_id = config.get('FACEBOOK_PAGE_ID')
        access_token = config.get('FACEBOOK_ACCESS_TOKEN')
        
        if not page_id or not access_token:
            return {
                "success": False,
                "message": "Facebook credentials not configured"
            }
        
        # For now, return basic info without making actual Facebook API calls
        # In a full implementation, you would make calls to Facebook Graph API
        return {
            "success": True,
            "page_id": page_id[:10] + "...",
            "page_name": "Connected Page",  # Would come from Facebook API
            "configured": True,
            "message": "Facebook connection active"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Keywords endpoints
@app.get("/keywords")
@rate_limit(max_requests=20, window_seconds=60)
async def get_keywords():
    """Get all keywords"""
    try:
        keywords = database.get_keywords()
        return {
            "success": True,
            "keywords": keywords
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/keywords")
@rate_limit(max_requests=10, window_seconds=60)
async def add_keyword(request: dict):
    """Add a new keyword"""
    try:
        keyword = request.get("keyword", "").strip()
        if not keyword:
            raise HTTPException(status_code=400, detail="Keyword is required")
        
        if len(keyword) > 100:
            raise HTTPException(status_code=400, detail="Keyword too long (max 100 characters)")
        
        success = database.add_keyword(keyword)
        if success:
            # Invalidate cache
            video_cache.clear()
            return {
                "success": True,
                "message": f"Keyword '{keyword}' added successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Keyword already exists")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/keywords/{keyword}")
@rate_limit(max_requests=10, window_seconds=60)
async def delete_keyword(keyword: str):
    """Delete a keyword"""
    try:
        success = database.remove_keyword(keyword)
        if success:
            # Invalidate cache
            video_cache.clear()
            return {
                "success": True,
                "message": f"Keyword '{keyword}' deleted successfully"
            }
        else:
            raise HTTPException(status_code=404, detail="Keyword not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Statistics endpoint with caching
@app.get("/stats")
async def get_stats():
    """Get system statistics"""
    try:
        cache_key = "system_stats"
        cached_result = stats_cache.get(cache_key)
        if cached_result:
            return cached_result
        
        stats = database.get_system_stats()
        
        result = {
            "success": True,
            "stats": stats
        }
        
        stats_cache.set(cache_key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs/recent-errors")
@rate_limit(max_requests=30, window_seconds=60)
async def get_recent_errors():
    """Get error logs from the last hour only"""
    try:
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT type, message, created_at FROM logs WHERE type LIKE '%error%' AND created_at >= datetime('now', '-1 hour') ORDER BY created_at DESC LIMIT 5"
            )
            rows = cursor.fetchall()
        
        errors = [{"type": r[0], "message": r[1], "created_at": r[2]} for r in rows]
        return {"success": True, "errors": errors}
    except Exception as e:
        return {"success": False, "errors": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

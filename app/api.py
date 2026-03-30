import os
import json
from typing import List, Dict, Optional
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
from .memory_cache import get_cached_config, invalidate_config_cache

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

# Initialize Redis and RQ
try:
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    redis_conn = redis.from_url(redis_url)
    # Use specific queues for different task types
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

    config_path = os.getenv('CONFIG_PATH', 'config/config.json')
    try:
        config = get_config()
        config.update(config_updates)
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        return True
    except Exception as e:
        database.log_error('api', f'Failed to update config: {str(e)}')
        return False

# API Endpoints

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "TikTok Video Collector API",
        "version": "1.0.0",
        "status": "running",
        "redis_connected": redis_conn is not None
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        stats = database.get_system_stats()
        
        # Test Redis connection
        redis_status = "connected" if redis_conn and redis_conn.ping() else "disconnected"
        
        return {
            "status": "healthy",
            "database": "connected",
            "redis": redis_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

# Keywords Management
@app.get("/keywords")
async def get_keywords():
    """Get all active keywords"""
    try:
        keywords = database.get_keywords()
        return {
            "success": True,
            "keywords": keywords,
            "count": len(keywords)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/keywords")
async def add_keyword(request: KeywordRequest):
    """Add a new keyword"""
    try:
        if not request.keyword.strip():
            raise HTTPException(status_code=400, detail="Keyword cannot be empty")
        
        success = database.add_keyword(request.keyword.strip())
        if success:
            database.log_info('api', f'Added keyword: {request.keyword}')
            return {"success": True, "message": f"Keyword '{request.keyword}' added successfully"}
        else:
            raise HTTPException(status_code=400, detail="Keyword already exists or failed to add")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/keywords/{keyword}")
async def remove_keyword(keyword: str):
    """Remove a keyword"""
    try:
        success = database.remove_keyword(keyword)
        if success:
            database.log_info('api', f'Removed keyword: {keyword}')
            return {"success": True, "message": f"Keyword '{keyword}' removed successfully"}
        else:
            raise HTTPException(status_code=404, detail="Keyword not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Videos Management
@app.get("/videos")
async def get_videos(
    downloaded: Optional[bool] = None,
    posted: Optional[bool] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0)
):
    """Get videos with optional filters"""
    try:
        videos = database.get_videos(downloaded=downloaded, posted=posted, limit=limit, offset=offset)
        return {
            "success": True,
            "videos": videos,
            "count": len(videos),
            "filters": {
                "downloaded": downloaded,
                "posted": posted,
                "limit": limit,
                "offset": offset
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/videos/pending-download")
async def get_pending_downloads(limit: int = Query(default=50, le=500)):
    """Get videos pending download"""
    try:
        videos = database.get_pending_downloads(limit)
        return {
            "success": True,
            "videos": videos,
            "count": len(videos)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/videos/pending-post")
async def get_pending_posts(limit: int = Query(default=15, le=500)):
    """Get videos pending posting"""
    try:
        videos = database.get_pending_posts(limit)
        return {
            "success": True,
            "videos": videos,
            "count": len(videos)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Video Management
@app.delete("/videos/pending-download")
async def clear_pending_downloads():
    """Delete all videos pending download"""
    try:
        deleted = database.clear_pending_downloads()
        return {
            "success": True,
            "deleted": deleted,
            "message": f"Cleared {deleted} videos pending download"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/videos/pending-post")
async def clear_pending_posts():
    """Delete all videos pending posting"""
    try:
        deleted = database.clear_pending_posts()
        return {
            "success": True,
            "deleted": deleted,
            "message": f"Cleared {deleted} videos pending posting"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/videos/{tiktok_id}")
async def delete_video(tiktok_id: str):
    """Delete a specific video by TikTok ID"""
    try:
        success = database.delete_video(tiktok_id)
        if success:
            return {
                "success": True,
                "message": f"Video {tiktok_id} deleted"
            }
        else:
            raise HTTPException(status_code=404, detail="Video not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Single-video task endpoints
@app.post("/tasks/download/{tiktok_id}")
async def download_single_video(tiktok_id: str):
    """Queue download for a specific video by TikTok ID"""
    try:
        if not downloader_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        # Fetch video_url from DB
        videos = database.get_videos(limit=1, offset=0)
        # Need a direct lookup — use get_pending_downloads and filter
        all_pending = database.get_pending_downloads(limit=500)
        video = next((v for v in all_pending if v['tiktok_id'] == tiktok_id), None)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found or already downloaded")
        job = downloader_queue.enqueue(
            download_video_task,
            tiktok_id=tiktok_id,
            video_url=video['video_url'],
            database_path=os.getenv('DATABASE_PATH', 'app/database.db'),
            download_path=os.getenv('DOWNLOAD_PATH', 'videos')
        )
        database.log_info('api', f'Queued download for video: {tiktok_id}')
        return {"success": True, "job_id": job.id, "message": f"Download queued for {tiktok_id}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/post/{tiktok_id}/schedule")
async def schedule_single_video_post(tiktok_id: str, scheduled_at: str):
    """Schedule a Facebook post for a specific video at a given ISO datetime (UTC)"""
    try:
        if not poster_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        page_id, access_token = get_facebook_credentials()
        if not page_id or not access_token:
            raise HTTPException(status_code=400, detail="Facebook credentials not configured")
        all_pending = database.get_pending_posts(limit=500)
        video = next((v for v in all_pending if v['tiktok_id'] == tiktok_id), None)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found, not downloaded, or already posted")
        scheduled_dt = datetime.fromisoformat(scheduled_at)
        job = poster_queue.enqueue_at(
            scheduled_dt,
            post_video_task,
            tiktok_id=tiktok_id,
            video_path=video['file_path'],
            caption=video.get('caption', ''),
            author=video.get('author', ''),
            hashtags=video.get('hashtags', []),
            page_id=page_id,
            access_token=access_token,
            database_path=os.getenv('DATABASE_PATH', 'app/database.db')
        )
        database.log_info('api', f'Scheduled post for video {tiktok_id} at {scheduled_at}')
        return {"success": True, "job_id": job.id, "message": f"Post scheduled for {scheduled_at}"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO format e.g. 2026-03-10T21:00:00")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        from .poster import FacebookPoster
        poster = FacebookPoster(database, page_id, access_token)
        result = poster.post_video_with_retry(
            tiktok_id=tiktok_id,
            video_path=video['file_path'],
            caption=video.get('caption', ''),
            author=video.get('author', ''),
            hashtags=video.get('hashtags', [])
        )
        
        if result and result.get('success'):
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

# Task Management
@app.post("/tasks/scrape-keyword/{keyword}")
async def scrape_keyword(keyword: str, background_tasks: BackgroundTasks):
    """Scrape videos for a single keyword (direct, no worker queue)"""
    try:
        from .scraper import TikTokScraper
        scraper = TikTokScraper(database)
        results = scraper.scrape_videos_by_keyword(keyword, count=50)
        
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
async def scrape_all_keywords():
    """Scrape all keywords"""
    try:
        if not scraper_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        
        job = scraper_queue.enqueue(
            scrape_all_keywords_task,
            database_path=os.getenv('DATABASE_PATH', 'app/database.db')
        )
        database.log_info('api', f'Scraping all keywords task queued: {job.id}')
        return {"success": True, "job_id": job.id, "message": "Scraping task queued for all keywords"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/scrape-unlimited")
async def unlimited_scraping():
    """Advanced unlimited scraping with multiple strategies"""
    try:
        if not scraper_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        
        job = scraper_queue.enqueue(
            unlimited_scraping_task,
            database_path=os.getenv('DATABASE_PATH', 'app/database.db')
        )
        database.log_info('api', f'Unlimited scraping task queued: {job.id}')
        return {"success": True, "job_id": job.id, "message": "Unlimited scraping task queued with multiple strategies"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/download-pending")
async def download_pending_videos(background_tasks: BackgroundTasks, limit: int = Query(default=50, le=100)):
    """Download pending videos (direct, no worker queue)"""
    try:
        from .downloader import VideoDownloader
        download_path = os.getenv('DOWNLOAD_PATH', 'videos')
        downloader = VideoDownloader(database, download_path)
        
        # Download pending videos directly
        result = downloader.download_pending_videos(limit)
        downloaded = result.get('downloaded', 0)
        failed = result.get('failed', 0)
        
        database.log_info('api', f'Downloaded {downloaded} videos, {failed} failed')
        
        return {
            "success": True,
            "message": f"Downloaded {downloaded} videos, {failed} failed",
            "downloaded": downloaded,
            "failed": failed
        }
    except Exception as e:
        database.log_error('api', f'Failed to download videos: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/post-pending")
async def post_pending_videos(background_tasks: BackgroundTasks, limit: int = Query(default=15, le=30)):
    """Start posting task for pending videos"""
    try:
        if not poster_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        
        page_id, access_token = get_facebook_credentials()
        if not page_id or not access_token:
            raise HTTPException(status_code=400, detail="Facebook credentials not configured")
        
        job = poster_queue.enqueue(
            post_pending_videos_task,
            page_id=page_id,
            access_token=access_token,
            database_path=os.getenv('DATABASE_PATH', 'app/database.db'),
            limit=limit
        )
        
        database.log_info('api', f'Queued posting task for {limit} pending videos')
        
        return {
            "success": True,
            "job_id": job.id,
            "message": f"Posting task queued for {limit} pending videos"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/cleanup")
async def cleanup_old_files(background_tasks: BackgroundTasks, days_old: int = Query(default=30, ge=1)):
    """Start cleanup task for old files"""
    try:
        if not cleanup_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        
        job = cleanup_queue.enqueue(
            cleanup_files_task,
            database_path=os.getenv('DATABASE_PATH', 'app/database.db'),
            download_path=os.getenv('DOWNLOAD_PATH', '/videos'),
            days_old=days_old
        )
        
        database.log_info('api', f'Queued cleanup task for files older than {days_old} days')
        
        return {
            "success": True,
            "job_id": job.id,
            "message": f"Cleanup task queued for files older than {days_old} days"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Statistics and Monitoring
@app.get("/tasks/status")
async def get_task_status():
    """Get task queue status"""
    try:
        if not scraper_queue:
            return {"success": True, "queues": {}, "workers": 0}
        
        from rq import Worker
        
        def queue_info(q):
            if not q:
                return {"pending": 0, "failed": 0}
            try:
                return {
                    "pending": len(q),
                    "failed": q.failed_job_registry.count
                }
            except Exception:
                return {"pending": 0, "failed": 0}
        
        try:
            workers = Worker.all(connection=redis_conn)
            worker_count = len(workers)
        except Exception:
            worker_count = 0
        
        return {
            "success": True,
            "queues": {
                "scraper": queue_info(scraper_queue),
                "downloader": queue_info(downloader_queue),
                "poster": queue_info(poster_queue)
            },
            "workers": worker_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/scheduler/next-post")
async def get_next_post_info():
    """Get information about the next scheduled post"""
    try:
        # Get next scheduled video
        next_video = database.get_next_scheduled_post()
        
        if not next_video:
            # No scheduled videos, get queue info
            pending_count = database.get_pending_posts_count()
            if pending_count > 0:
                # Read interval settings from config file directly
                config = get_config()
                min_interval = config.get('MIN_POST_INTERVAL', 10)
                max_interval = config.get('MAX_POST_INTERVAL', 30)
                
                return {
                    "success": True,
                    "next_post_time": None,
                    "queue_count": pending_count,
                    "mode": "queue_order",
                    "interval_range": f"{min_interval}-{max_interval} minutes",
                    "message": f"Next post in {min_interval}-{max_interval} minutes (queue order)"
                }
            else:
                return {
                    "success": True,
                    "next_post_time": None,
                    "queue_count": 0,
                    "mode": "no_content",
                    "message": "No videos ready to post"
                }
        
        # Has scheduled video
        scheduled_time = next_video.get('scheduled_time')
        if scheduled_time:
            try:
                scheduled_dt = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
                formatted_time = scheduled_dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                formatted_time = scheduled_time
            
            pending_count = database.get_pending_posts_count()
            return {
                "success": True,
                "next_post_time": formatted_time,
                "queue_count": pending_count,
                "mode": "scheduled",
                "tiktok_id": next_video.get('tiktok_id'),
                "message": f"Scheduled for {formatted_time}"
            }
        
        return {
            "success": True,
            "next_post_time": None,
            "queue_count": 0,
            "mode": "unknown",
            "message": "Unable to determine next post time"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_system_stats():
    """Get system statistics"""
    try:
        stats = database.get_system_stats()
        config = get_config()
        
        # Add queue information if available
        queue_info = {}
        if scraper_queue:
            try:
                total_pending = sum(len(q) for q in [scraper_queue, downloader_queue, poster_queue, cleanup_queue] if q)
                queue_info = {
                    "pending_jobs": total_pending,
                    "scraper": len(scraper_queue),
                    "downloader": len(downloader_queue),
                    "poster": len(poster_queue),
                    "cleanup": len(cleanup_queue),
                    "failed_jobs": scraper_queue.failed_job_registry.count
                }
            except:
                queue_info = {"status": "error"}
        
        return {
            "success": True,
            "database": stats,
            "config": config,
            "queue": queue_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs")
async def get_logs(limit: int = Query(default=100, le=500)):
    """Get recent system logs"""
    try:
        logs = database.get_recent_logs(limit)
        return {
            "success": True,
            "logs": logs,
            "count": len(logs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/facebook/exchange-token")
async def exchange_facebook_token(
    short_lived_token: str,
    app_id: str,
    app_secret: str,
    page_id: str = None
):
    """Exchange short-lived user token for a permanent page access token and save it"""
    try:
        import requests as req
        graph = "https://graph.facebook.com/v18.0"

        # Step 1: Exchange short-lived → long-lived user token (60 days)
        r1 = req.get(f"{graph}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token
        }, timeout=10)
        if r1.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {r1.json().get('error', {}).get('message', r1.text)}")
        long_lived_token = r1.json().get("access_token")
        if not long_lived_token:
            raise HTTPException(status_code=400, detail="No long-lived token returned")

        # Step 2: Get permanent page access token
        _, _cfg_page_id = get_facebook_credentials()
        pid = page_id or _cfg_page_id
        if not pid:
            raise HTTPException(status_code=400, detail="page_id is required")
        r2 = req.get(f"{graph}/{pid}", params={
            "fields": "access_token,name",
            "access_token": long_lived_token
        }, timeout=10)
        if r2.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Page token fetch failed: {r2.json().get('error', {}).get('message', r2.text)}")
        data = r2.json()
        page_token = data.get("access_token")
        page_name  = data.get("name", "Unknown")
        if not page_token:
            raise HTTPException(status_code=400, detail="No page token returned — ensure the user manages this page")

        # Step 3: Save both page_id and permanent token to config
        update_config({"FACEBOOK_PAGE_ID": pid, "FACEBOOK_ACCESS_TOKEN": page_token})
        database.log_info('api', f'Saved permanent page token for: {page_name}')

        return {
            "success": True,
            "page_name": page_name,
            "page_id": pid,
            "message": f"Permanent page token saved for '{page_name}'. It will not expire unless permissions are revoked."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/facebook/stats")
async def get_facebook_stats():
    """Get Facebook page statistics"""
    try:
        page_id, access_token = get_facebook_credentials()
        if not page_id or not access_token:
            raise HTTPException(status_code=400, detail="Facebook credentials not configured")
        
        if not poster_queue:
            # Direct call if RQ not available
            from .poster import FacebookPoster
            poster = FacebookPoster(database, page_id, access_token)
            result = poster.get_page_stats()
        else:
            job = poster_queue.enqueue(
                get_facebook_stats_task,
                page_id=page_id,
                access_token=access_token,
                database_path=os.getenv('DATABASE_PATH', 'app/database.db')
            )
            result = {
                "success": True,
                "job_id": job.id,
                "message": "Facebook stats task queued"
            }
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Configuration Management
@app.get("/config")
async def get_system_config():
    """Get system configuration"""
    try:
        config = get_config()
        return {
            "success": True,
            "config": config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/config")
async def update_system_config(config_update: ConfigUpdate):
    """Update system configuration"""
    try:
        updates = {}
        if config_update.facebook_page_id is not None:
            updates["FACEBOOK_PAGE_ID"] = config_update.facebook_page_id
        if config_update.facebook_access_token is not None:
            updates["FACEBOOK_ACCESS_TOKEN"] = config_update.facebook_access_token
        if config_update.min_posts_per_day is not None:
            updates["MIN_POSTS_PER_DAY"] = config_update.min_posts_per_day
        if config_update.max_posts_per_day is not None:
            updates["MAX_POSTS_PER_DAY"] = config_update.max_posts_per_day
        if config_update.min_scrape_interval is not None:
            updates["MIN_SCRAPE_INTERVAL"] = config_update.min_scrape_interval
        if config_update.max_scrape_interval is not None:
            updates["MAX_SCRAPE_INTERVAL"] = config_update.max_scrape_interval
        if config_update.min_post_interval is not None:
            updates["MIN_POST_INTERVAL"] = config_update.min_post_interval
        if config_update.max_post_interval is not None:
            updates["MAX_POST_INTERVAL"] = config_update.max_post_interval
        
        if not updates:
            raise HTTPException(status_code=400, detail="No valid configuration updates provided")
        
        success = update_config(updates)
        if success:
            database.log_info('api', f'Updated configuration: {updates}')
            return {
                "success": True,
                "message": "Configuration updated successfully",
                "updates": updates
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update configuration")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Manual Actions
@app.post("/actions/download-video/{tiktok_id}")
async def manual_download_video(tiktok_id: str):
    """Manually download a specific video"""
    try:
        # This would need to get video URL from database first
        # For now, return placeholder
        return {
            "success": True,
            "message": f"Manual download initiated for {tiktok_id}",
            "note": "This endpoint needs implementation to get video URL from database"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/actions/post-video/{tiktok_id}")
async def manual_post_video(tiktok_id: str, request: VideoPostRequest):
    """Manually post a specific video"""
    try:
        # This would need to get video details from database first
        # For now, return placeholder
        return {
            "success": True,
            "message": f"Manual posting initiated for {tiktok_id}",
            "note": "This endpoint needs implementation to get video details from database"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

import os
import json
from typing import List, Dict, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import redis
from rq import Queue
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .database import Database
from .scraper import scrape_keyword_task, scrape_all_keywords_task
from .downloader import download_video_task, download_pending_videos_task, cleanup_files_task
from .poster import post_video_task, post_pending_videos_task, get_facebook_stats_task

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
    """Get system configuration"""
    config_path = os.getenv('CONFIG_PATH', 'config/config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except:
        return {
            "MIN_POSTS_PER_DAY": 10,
            "MAX_POSTS_PER_DAY": 15,
            "MIN_SCRAPE_INTERVAL": 20,
            "MAX_SCRAPE_INTERVAL": 60,
            "MIN_POST_INTERVAL": 30,
            "MAX_POST_INTERVAL": 90
        }

def get_facebook_credentials():
    """Get Facebook credentials from env vars, falling back to config.json"""
    config = get_config()
    page_id = os.getenv('FACEBOOK_PAGE_ID') or config.get('FACEBOOK_PAGE_ID')
    access_token = os.getenv('FACEBOOK_ACCESS_TOKEN') or config.get('FACEBOOK_ACCESS_TOKEN')
    return page_id, access_token

def update_config(config_updates: Dict):
    """Update system configuration"""
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
    """Queue Facebook post for a specific downloaded video"""
    try:
        if not poster_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        page_id, access_token = get_facebook_credentials()
        if not page_id or not access_token:
            raise HTTPException(status_code=400, detail="Facebook credentials not configured")
        # Get video details from pending posts
        all_pending = database.get_pending_posts(limit=500)
        video = next((v for v in all_pending if v['tiktok_id'] == tiktok_id), None)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found, not downloaded, or already posted")
        job = poster_queue.enqueue(
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
        database.log_info('api', f'Queued post for video: {tiktok_id}')
        return {"success": True, "job_id": job.id, "message": f"Post queued for {tiktok_id}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Task Management
@app.post("/tasks/scrape-keyword/{keyword}")
async def scrape_keyword(keyword: str, background_tasks: BackgroundTasks):
    """Start scraping task for a single keyword"""
    try:
        if not scraper_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        
        job = scraper_queue.enqueue(
            scrape_keyword_task,
            keyword=keyword,
            database_path=os.getenv('DATABASE_PATH', 'app/database.db')
        )
        
        database.log_info('api', f'Queued scraping task for keyword: {keyword}')
        
        return {
            "success": True,
            "job_id": job.id,
            "message": f"Scraping task queued for keyword: {keyword}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/scrape-all")
async def scrape_all_keywords(background_tasks: BackgroundTasks):
    """Start scraping task for all keywords"""
    try:
        if not scraper_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        
        job = scraper_queue.enqueue(
            scrape_all_keywords_task,
            database_path=os.getenv('DATABASE_PATH', 'app/database.db')
        )
        
        database.log_info('api', 'Queued scraping task for all keywords')
        
        return {
            "success": True,
            "job_id": job.id,
            "message": "Scraping task queued for all keywords"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/download-pending")
async def download_pending_videos(background_tasks: BackgroundTasks, limit: int = Query(default=50, le=100)):
    """Start download task for pending videos"""
    try:
        if not downloader_queue:
            raise HTTPException(status_code=503, detail="Redis/RQ not available")
        
        job = downloader_queue.enqueue(
            download_pending_videos_task,
            database_path=os.getenv('DATABASE_PATH', 'app/database.db'),
            download_path=os.getenv('DOWNLOAD_PATH', '/videos'),
            limit=limit
        )
        
        database.log_info('api', f'Queued download task for {limit} pending videos')
        
        return {
            "success": True,
            "job_id": job.id,
            "message": f"Download task queued for {limit} pending videos"
        }
    except Exception as e:
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

@app.get("/tasks/status")
async def get_task_status():
    """Get current task queue status and ETAs"""
    try:
        from rq.job import Job
        status = {}
        for name, q in [('scraper', scraper_queue), ('downloader', downloader_queue), ('poster', poster_queue), ('cleanup', cleanup_queue)]:
            if not q:
                continue
            pending = []
            for job_id in q.get_job_ids():
                try:
                    job = Job.fetch(job_id, connection=redis_conn)
                    pending.append({
                        'id': job.id[:8],
                        'func': job.func_name,
                        'created_at': job.created_at.isoformat() if job.created_at else None,
                        'status': job.get_status(),
                        'timeout': job.timeout
                    })
                except:
                    continue
            status[name] = {
                'pending': len(q),
                'failed': q.failed_job_registry.count,
                'jobs': pending[:5]  # show up to 5 jobs
            }
        return {
            "success": True,
            "queues": status,
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

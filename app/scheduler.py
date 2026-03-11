import os
import json
import time
import random
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from .database import Database
from .scraper import scrape_keyword_task, scrape_all_keywords_task
from .downloader import download_pending_videos_task, cleanup_files_task
from .poster import post_pending_videos_task, get_facebook_stats_task

class TikTokScheduler:
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.database = Database()
        self.scheduler = AsyncIOScheduler()
        self.running = False
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize scheduler
        self._setup_scheduler()
    
    def _load_config(self) -> dict:
        """Load system configuration"""
        try:
            config_path = os.getenv('CONFIG_PATH', 'config/config.json')
            with open(config_path, 'r') as f:
                return json.load(f)
        except:
            return {
                'MIN_POSTS_PER_DAY': 5,
                'MAX_POSTS_PER_DAY': 15,
                'MIN_POST_INTERVAL': 10,  # minutes
                'MAX_POST_INTERVAL': 30,  # minutes
                'SCRAPE_INTERVAL': 30,    # minutes
                'CLEANUP_INTERVAL': 24    # hours
            }
    
    def _setup_scheduler(self):
        """Setup scheduled tasks"""
        try:
            # Scrape all keywords every SCRAPE_INTERVAL minutes
            self.scheduler.add_job(
                func=self._scrape_all_keywords,
                trigger=IntervalTrigger(minutes=self.config.get('SCRAPE_INTERVAL', 30)),
                id='scrape_all_keywords',
                name='Scrape all keywords',
                replace_existing=True,
                max_instances=1
            )
            
            # Download pending videos every 15 minutes
            self.scheduler.add_job(
                func=self._download_pending_videos,
                trigger=IntervalTrigger(minutes=15),
                id='download_pending',
                name='Download pending videos',
                replace_existing=True,
                max_instances=1
            )
            
            # Post to Facebook check every 5 minutes (actual posting uses min-max intervals)
            self.scheduler.add_job(
                func=self._post_to_facebook,
                trigger=IntervalTrigger(minutes=5),
                id='post_facebook',
                name='Post to Facebook',
                replace_existing=True,
                max_instances=1
            )
            
            # Daily cleanup at 2 AM
            self.scheduler.add_job(
                func=self._cleanup_files,
                trigger=CronTrigger(hour=2, minute=0),
                id='daily_cleanup',
                name='Daily cleanup',
                replace_existing=True,
                max_instances=1
            )
            
            # Update statistics every hour
            self.scheduler.add_job(
                func=self._update_statistics,
                trigger=IntervalTrigger(hours=1),
                id='update_stats',
                name='Update statistics',
                replace_existing=True,
                max_instances=1
            )
            
            # Sync Facebook stats every 6 hours
            self.scheduler.add_job(
                func=self._sync_facebook_stats,
                trigger=IntervalTrigger(hours=6),
                id='sync_facebook',
                name='Sync Facebook stats',
                replace_existing=True,
                max_instances=1
            )
            
            self.database.log_info('scheduler', 'Scheduler configured with all tasks')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Failed to setup scheduler: {str(e)}')
            raise
    
    async def start(self):
        """Start the scheduler"""
        try:
            self.running = True
            self.scheduler.start()
            self.database.log_info('scheduler', 'Scheduler started successfully')
            
            # Keep the scheduler running
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.database.log_error('scheduler', f'Scheduler error: {str(e)}')
            raise
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        self.database.log_info('scheduler', 'Scheduler stopped')
    
    async def _scrape_all_keywords(self):
        """Scrape all keywords task"""
        try:
            # Check if we should run scraping (avoid rate limiting)
            last_scrape = self._get_last_run_time('scraping')
            scrape_interval = self.config.get('SCRAPE_INTERVAL', 30)
            
            if last_scrape and (datetime.now() - last_scrape).total_seconds() < (scrape_interval * 60):
                return
            
            # Get keywords
            keywords = self.database.get_keywords()
            if not keywords:
                self.database.log_info('scheduler', 'No keywords configured for scraping')
                return
            
            # Run scraping task (this would normally be queued to RQ)
            # For now, we'll simulate the task
            total_videos = 0
            for keyword in keywords:
                try:
                    # In production, this would be: queue.enqueue(scrape_keyword_task, ...)
                    # For demo purposes, we'll just log
                    self.database.log_info('scheduler', f'Would scrape keyword: {keyword}')
                    total_videos += 20  # Simulated count
                except Exception as e:
                    self.database.log_error('scheduler', f'Failed to scrape {keyword}: {str(e)}')
            
            # Update last run time
            self._set_last_run_time('scraping', datetime.now())
            
            # Update daily stats
            self.database.update_daily_stats(scraped=total_videos)
            
            self.database.log_info('scheduler', f'Scraping completed for {len(keywords)} keywords, {total_videos} videos')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Scraping task failed: {str(e)}')
    
    async def _download_pending_videos(self):
        """Download pending videos task"""
        try:
            # Get pending videos
            pending_videos = self.database.get_pending_downloads(10)
            if not pending_videos:
                return
            
            downloaded_count = 0
            for video in pending_videos:
                try:
                    # In production, this would be: queue.enqueue(download_video_task, ...)
                    # For demo purposes, we'll simulate success
                    self.database.update_video_downloaded(video['tiktok_id'], f"/videos/{video['tiktok_id']}.mp4")
                    downloaded_count += 1
                    self.database.log_info('scheduler', f'Would download video: {video["tiktok_id"]}')
                except Exception as e:
                    self.database.log_error('scheduler', f'Failed to download {video["tiktok_id"]}: {str(e)}')
            
            # Update daily stats
            if downloaded_count > 0:
                self.database.update_daily_stats(downloaded=downloaded_count)
            
            self.database.log_info('scheduler', f'Download task completed: {downloaded_count}/{len(pending_videos)} videos')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Download task failed: {str(e)}')
    
    async def _post_to_facebook(self):
        """Post to Facebook task"""
        try:
            # Check daily post limits (min-max)
            stats = self.database.get_system_stats()
            posts_today = stats['today']['posted']
            min_posts = self.config.get('MIN_POSTS_PER_DAY', 5)
            max_posts = self.config.get('MAX_POSTS_PER_DAY', 15)
            
            # Don't post if we've reached max for today
            if posts_today >= max_posts:
                self.database.log_info('scheduler', f'Daily post limit reached: {posts_today}/{max_posts}')
                return
            
            # Check if we should post more today (target minimum)
            if posts_today >= min_posts:
                # We've hit minimum, now check if we want to post more (random chance)
                remaining_capacity = max_posts - posts_today
                if remaining_capacity > 0:
                    # 50% chance to post more if we haven't hit max
                    if random.random() > 0.5:
                        self.database.log_info('scheduler', f'Minimum posts reached ({posts_today}), skipping additional posting')
                        return
            
            # Check posting interval (use min-max range)
            last_post = self._get_last_run_time('posting')
            min_interval = self.config.get('MIN_POST_INTERVAL', 10)  # Default 10 minutes
            max_interval = self.config.get('MAX_POST_INTERVAL', 30)  # Default 30 minutes
            
            if last_post:
                # Use random interval within min-max range
                last_interval = (datetime.now() - last_post).total_seconds() / 60
                if last_interval < min_interval:
                    return  # Too soon since last post
            
            # Get pending videos
            pending_videos = self.database.get_pending_posts(1)
            if not pending_videos:
                return
            
            video = pending_videos[0]
            
            # Check Facebook credentials from config.json first, then env vars
            config_path = os.getenv('CONFIG_PATH', 'config/config.json')
            page_id = os.getenv('FACEBOOK_PAGE_ID')
            access_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
            
            if not page_id or not access_token:
                try:
                    with open(config_path, 'r') as f:
                        cfg = json.load(f)
                    page_id = cfg.get('FACEBOOK_PAGE_ID', page_id)
                    access_token = cfg.get('FACEBOOK_ACCESS_TOKEN', access_token)
                except Exception:
                    pass
            
            if not page_id or not access_token:
                self.database.log_warning('scheduler', 'Facebook credentials not configured')
                return
            
            try:
                from .poster import FacebookPoster
                poster = FacebookPoster(self.database, page_id, access_token)
                result = poster.post_video_with_retry(
                    tiktok_id=video['tiktok_id'],
                    video_path=video.get('file_path', ''),
                    caption=video.get('caption', ''),
                    author=video.get('author', ''),
                    hashtags=video.get('hashtags', [])
                )
                
                if result and result.get('success'):
                    self.database.update_daily_stats(posted=1)
                    self._set_last_run_time('posting', datetime.now())
                    self.database.log_info('scheduler', f'Posted video to Facebook: {video["tiktok_id"]} (post_id: {result.get("facebook_post_id", "unknown")})')
                else:
                    error_msg = result.get('message', 'Unknown error') if result else 'No response from poster'
                    self.database.log_error('scheduler', f'Failed to post {video["tiktok_id"]}: {error_msg}')
                
            except Exception as e:
                self.database.log_error('scheduler', f'Failed to post {video["tiktok_id"]}: {str(e)}')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Facebook posting task failed: {str(e)}')
    
    async def _cleanup_files(self):
        """Cleanup old files task"""
        try:
            # In production, this would be: queue.enqueue(cleanup_files_task, ...)
            # For demo purposes, we'll just log
            self.database.log_info('scheduler', 'Would run daily cleanup task')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Cleanup task failed: {str(e)}')
    
    async def _update_statistics(self):
        """Update system statistics"""
        try:
            stats = self.database.get_system_stats()
            self.database.log_info('scheduler', f'System stats: {stats}')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Stats update failed: {str(e)}')
    
    async def _sync_facebook_stats(self):
        """Sync Facebook page statistics"""
        try:
            # Check Facebook credentials
            page_id = os.getenv('FACEBOOK_PAGE_ID')
            access_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
            
            if not page_id or not access_token:
                return
            
            # In production, this would be: queue.enqueue(get_facebook_stats_task, ...)
            # For demo purposes, we'll simulate
            self.database.log_info('scheduler', 'Would sync Facebook page statistics')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Facebook stats sync failed: {str(e)}')
    
    def _get_last_run_time(self, task_type: str) -> datetime:
        """Get last run time for a task type"""
        try:
            import redis
            redis_conn = redis.from_url(self.redis_url)
            key = f'scheduler:last_run:{task_type}'
            timestamp = redis_conn.get(key)
            if timestamp:
                return datetime.fromisoformat(timestamp.decode())
        except:
            pass
        return None
    
    def _set_last_run_time(self, task_type: str, run_time: datetime):
        """Set last run time for a task type"""
        try:
            import redis
            redis_conn = redis.from_url(self.redis_url)
            key = f'scheduler:last_run:{task_type}'
            redis_conn.set(key, run_time.isoformat(), ex=86400 * 7)  # Keep for 7 days
        except Exception as e:
            self.database.log_error('scheduler', f'Failed to set last run time: {str(e)}')
    
    def get_job_status(self) -> dict:
        """Get status of all scheduled jobs"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger),
                'max_instances': job.max_instances
            })
        
        return {
            'running': self.running,
            'jobs': jobs,
            'config': self.config
        }

# Standalone scheduler function for RQ
def run_scheduler_task(redis_url: str = None, database_path: str = "app/database.db"):
    """Run scheduler as a background task"""
    import asyncio
    
    scheduler = TikTokScheduler(redis_url)
    
    try:
        asyncio.run(scheduler.start())
    except KeyboardInterrupt:
        scheduler.stop()
    except Exception as e:
        scheduler.database.log_error('scheduler', f'Scheduler task failed: {str(e)}')

if __name__ == "__main__":
    # Run scheduler standalone
    import asyncio
    
    scheduler = TikTokScheduler()
    
    try:
        asyncio.run(scheduler.start())
    except KeyboardInterrupt:
        scheduler.stop()
        print("Scheduler stopped by user")

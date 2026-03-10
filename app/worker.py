import os
import random
import redis
import json
import time
import asyncio
from datetime import datetime, timedelta
from rq import Queue, Worker
from rq.job import Job
from .database import Database
from .scraper import scrape_keyword_task, scrape_all_keywords_task
from .downloader import download_video_task, download_pending_videos_task, cleanup_files_task
from .poster import post_video_task, post_pending_videos_task, get_facebook_stats_task

class TaskWorker:
    def __init__(self, redis_url: str = None, queues: list = None):
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.queues = queues or ['scraper', 'downloader', 'poster', 'cleanup']
        self.database = Database()
        self.redis_conn = None
        self.worker = None
        
        self._setup_connection()
    
    def _setup_connection(self):
        """Setup Redis connection and worker"""
        try:
            self.redis_conn = redis.from_url(self.redis_url)
            
            # Test connection
            self.redis_conn.ping()
            
            # Create queues
            self.queues = [Queue(name, connection=self.redis_conn) for name in self.queues]
            
            # Create worker
            self.worker = Worker(
                self.queues,
                connection=self.redis_conn,
                name='tiktok-worker',
                default_result_ttl=86400  # 24 hours
            )
            
            self.database.log_info('worker', f'Worker initialized with queues: {[q.name for q in self.queues]}')
            
        except Exception as e:
            self.database.log_error('worker', f'Failed to setup worker: {str(e)}')
            raise
    
    def start_worker(self):
        """Start the worker process"""
        try:
            self.database.log_info('worker', 'Starting worker process')
            
            # Register signal handlers for graceful shutdown
            import signal
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            # Start working
            self.worker.work(with_scheduler=True)
            
        except KeyboardInterrupt:
            self.database.log_info('worker', 'Worker stopped by user')
        except Exception as e:
            self.database.log_error('worker', f'Worker error: {str(e)}')
            raise
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.database.log_info('worker', f'Received signal {signum}, shutting down gracefully')
        if self.worker:
            self.worker.stop()
    
    def get_queue_stats(self) -> dict:
        """Get statistics for all queues"""
        stats = {}
        
        for queue in self.queues:
            try:
                stats[queue.name] = {
                    'pending': len(queue),
                    'failed': queue.failed_job_registry.count,
                    'scheduled': queue.scheduled_job_registry.count,
                    'started': queue.started_job_registry.count,
                    'deferred': queue.deferred_job_registry.count,
                    'finished': queue.finished_job_registry.count
                }
            except Exception as e:
                stats[queue.name] = {'error': str(e)}
        
        return stats
    
    def cleanup_failed_jobs(self, max_age_hours: int = 24):
        """Clean up old failed jobs"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            cleaned_count = 0
            
            for queue in self.queues:
                failed_jobs = queue.failed_job_registry.get_job_ids()
                
                for job_id in failed_jobs:
                    try:
                        job = Job.fetch(job_id, connection=self.redis_conn)
                        if job.created_at < cutoff_time:
                            job.delete()
                            cleaned_count += 1
                    except:
                        continue
            
            self.database.log_info('worker', f'Cleaned up {cleaned_count} old failed jobs')
            return cleaned_count
            
        except Exception as e:
            self.database.log_error('worker', f'Failed to cleanup jobs: {str(e)}')
            return 0

class SchedulerService:
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.database = Database()
        self.redis_conn = None
        self.queue = None
        self.running = False
        
        self._setup_connection()
    
    def _setup_connection(self):
        """Setup Redis connection"""
        try:
            self.redis_conn = redis.from_url(self.redis_url)
            self.scraper_queue = Queue('scraper', connection=self.redis_conn)
            self.downloader_queue = Queue('downloader', connection=self.redis_conn)
            self.poster_queue = Queue('poster', connection=self.redis_conn)
            self.cleanup_queue = Queue('cleanup', connection=self.redis_conn)
            self.queue = self.scraper_queue  # default alias
            self.database.log_info('scheduler', 'Scheduler initialized')
        except Exception as e:
            self.database.log_error('scheduler', f'Failed to setup scheduler: {str(e)}')
            raise
    
    def start_scheduler(self):
        """Start the scheduler service"""
        self.running = True
        self.database.log_info('scheduler', 'Starting scheduler service')
        
        try:
            while self.running:
                current_time = datetime.now()
                
                # Schedule scraping tasks
                self._schedule_scraping_tasks(current_time)
                
                # Schedule download tasks
                self._schedule_download_tasks(current_time)
                
                # Schedule posting tasks
                self._schedule_posting_tasks(current_time)
                
                # Schedule cleanup tasks
                self._schedule_cleanup_tasks(current_time)
                
                # Sleep for a minute before next check
                time.sleep(60)
                
        except KeyboardInterrupt:
            self.database.log_info('scheduler', 'Scheduler stopped by user')
        except Exception as e:
            self.database.log_error('scheduler', f'Scheduler error: {str(e)}')
        finally:
            self.running = False
    
    def _schedule_scraping_tasks(self, current_time: datetime):
        """Schedule scraping tasks based on configuration"""
        try:
            config = self._get_config()
            min_scrape = config.get('MIN_SCRAPE_INTERVAL', config.get('SCRAPE_INTERVAL', 20))
            max_scrape = config.get('MAX_SCRAPE_INTERVAL', min_scrape)
            scrape_interval = random.randint(min(min_scrape, max_scrape), max(min_scrape, max_scrape))
            
            # Check if we should run scraping now
            last_scrape = self._get_last_run_time('scraping')
            if last_scrape and (current_time - last_scrape).total_seconds() < (scrape_interval * 60):
                return
            
            # Get keywords to scrape
            keywords = self.database.get_keywords()
            if not keywords:
                return
            
            # Schedule scraping for each keyword
            for keyword in keywords:
                try:
                    self.scraper_queue.enqueue(
                        scrape_keyword_task,
                        keyword=keyword,
                        database_path=os.getenv('DATABASE_PATH', 'app/database.db'),
                        ttl=3600,  # 1 hour timeout
                        result_ttl=86400  # 24 hours result retention
                    )
                except Exception as e:
                    self.database.log_error('scheduler', f'Failed to schedule scraping for {keyword}: {str(e)}')
            
            # Update last run time
            self._set_last_run_time('scraping', current_time)
            self.database.log_info('scheduler', f'Scheduled scraping for {len(keywords)} keywords')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Failed to schedule scraping: {str(e)}')
    
    def _schedule_download_tasks(self, current_time: datetime):
        """Schedule download tasks for pending videos"""
        try:
            # Check if there are pending downloads
            pending_videos = self.database.get_pending_downloads(10)  # Check up to 10
            if not pending_videos:
                return
            
            # Schedule download task
            self.downloader_queue.enqueue(
                download_pending_videos_task,
                database_path=os.getenv('DATABASE_PATH', 'app/database.db'),
                download_path=os.getenv('DOWNLOAD_PATH', '/videos'),
                limit=10,
                ttl=3600,
                result_ttl=86400
            )
            
            self.database.log_info('scheduler', f'Scheduled download task for {len(pending_videos)} videos')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Failed to schedule downloads: {str(e)}')
    
    def _schedule_posting_tasks(self, current_time: datetime):
        """Schedule posting tasks based on daily limits"""
        try:
            config = self._get_config()
            min_posts = config.get('MIN_POSTS_PER_DAY', config.get('MAX_POSTS_PER_DAY', 10))
            max_posts_per_day = config.get('MAX_POSTS_PER_DAY', 15)
            daily_limit = random.randint(min(min_posts, max_posts_per_day), max(min_posts, max_posts_per_day))
            min_post_iv = config.get('MIN_POST_INTERVAL', config.get('POST_INTERVAL', 30))
            max_post_iv = config.get('MAX_POST_INTERVAL', min_post_iv)
            post_interval = random.randint(min(min_post_iv, max_post_iv), max(min_post_iv, max_post_iv))
            
            # Check daily post count
            stats = self.database.get_system_stats()
            posts_today = stats['today']['posted']
            
            if posts_today >= daily_limit:
                return
            
            # Check if we should post now
            last_post = self._get_last_run_time('posting')
            if last_post and (current_time - last_post).total_seconds() < (post_interval * 60):
                return
            
            # Get pending videos to post
            pending_posts = self.database.get_pending_posts(1)  # Post one at a time
            if not pending_posts:
                return
            
            video = pending_posts[0]
            
            # Get Facebook credentials — env vars first, then config.json
            config = self._get_config()
            page_id = os.getenv('FACEBOOK_PAGE_ID') or config.get('FACEBOOK_PAGE_ID')
            access_token = os.getenv('FACEBOOK_ACCESS_TOKEN') or config.get('FACEBOOK_ACCESS_TOKEN')
            
            if not page_id or not access_token:
                self.database.log_warning('scheduler', 'Facebook credentials not configured')
                return
            
            # Schedule posting task
            self.poster_queue.enqueue(
                post_pending_videos_task,
                page_id=page_id,
                access_token=access_token,
                database_path=os.getenv('DATABASE_PATH', 'app/database.db'),
                limit=1,
                ttl=1800,  # 30 minutes timeout for posting
                result_ttl=86400
            )
            
            # Update last run time
            self._set_last_run_time('posting', current_time)
            self.database.log_info('scheduler', f'Scheduled posting for video: {video["tiktok_id"]}')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Failed to schedule posting: {str(e)}')
    
    def _schedule_cleanup_tasks(self, current_time: datetime):
        """Schedule cleanup tasks (run once daily)"""
        try:
            # Run cleanup at 2 AM daily
            if current_time.hour != 2 or current_time.minute != 0:
                return
            
            # Check if cleanup already ran today
            last_cleanup = self._get_last_run_time('cleanup')
            if last_cleanup and last_cleanup.date() == current_time.date():
                return
            
            # Schedule cleanup task
            self.cleanup_queue.enqueue(
                cleanup_files_task,
                database_path=os.getenv('DATABASE_PATH', 'app/database.db'),
                download_path=os.getenv('DOWNLOAD_PATH', '/videos'),
                days_old=30,
                ttl=1800,
                result_ttl=86400
            )
            
            # Update last run time
            self._set_last_run_time('cleanup', current_time)
            self.database.log_info('scheduler', 'Scheduled daily cleanup task')
            
        except Exception as e:
            self.database.log_error('scheduler', f'Failed to schedule cleanup: {str(e)}')
    
    def _get_config(self) -> dict:
        """Get system configuration"""
        try:
            config_path = os.getenv('CONFIG_PATH', 'config/config.json')
            with open(config_path, 'r') as f:
                return json.load(f)
        except:
            return {
                'MAX_POSTS_PER_DAY': 15,
                'SCRAPE_INTERVAL': 30,
                'POST_INTERVAL': 60
            }
    
    def _get_last_run_time(self, task_type: str) -> datetime:
        """Get last run time for a task type"""
        try:
            key = f'scheduler:last_run:{task_type}'
            timestamp = self.redis_conn.get(key)
            if timestamp:
                return datetime.fromisoformat(timestamp.decode())
        except:
            pass
        return None
    
    def _set_last_run_time(self, task_type: str, run_time: datetime):
        """Set last run time for a task type"""
        try:
            key = f'scheduler:last_run:{task_type}'
            self.redis_conn.set(key, run_time.isoformat(), ex=86400 * 7)  # Keep for 7 days
        except Exception as e:
            self.database.log_error('scheduler', f'Failed to set last run time: {str(e)}')
    
    def stop_scheduler(self):
        """Stop the scheduler service"""
        self.running = False
        self.database.log_info('scheduler', 'Scheduler service stopped')

def main():
    """Main function to run worker or scheduler"""
    import sys
    
    mode = os.getenv('WORKER_MODE', 'worker')  # 'worker' or 'scheduler'
    
    if mode == 'scheduler':
        # Run scheduler
        scheduler = SchedulerService()
        scheduler.start_scheduler()
    else:
        # Run worker
        worker = TaskWorker()
        worker.start_worker()

if __name__ == "__main__":
    main()

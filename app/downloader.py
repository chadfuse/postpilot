import os
import time
import requests
import yt_dlp
from typing import Dict, Optional
from datetime import datetime
from .database import Database

TIKWM_API = "https://www.tikwm.com/api/"

class VideoDownloader:
    def __init__(self, database: Database, download_path: str = "videos", max_retries: int = 3):
        self.database = database
        self.download_path = download_path
        self.max_retries = max_retries
        
        # Ensure download directory exists
        os.makedirs(download_path, exist_ok=True)
        
        # Configure yt-dlp as fallback
        self.ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(download_path, '%(id)s.%(ext)s'),
            'writethumbnail': False,
            'writeinfojson': False,
            'quiet': True,
            'no_check_certificates': True,
            'ignoreerrors': False,
            'restrictfilenames': True,
            'socket_timeout': 30,
            'retries': 3,
            'cookiesfrombrowser': ('chrome',),
            'impersonate': 'chrome',
        }

    def _download_direct_url(self, tiktok_id: str, play_url: str) -> Dict[str, any]:
        """Download from a direct CDN URL (already resolved, no watermark)"""
        try:
            file_path = os.path.join(self.download_path, f"{tiktok_id}.mp4")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            video_resp = requests.get(play_url, stream=True, timeout=60, headers=headers)
            video_resp.raise_for_status()

            with open(file_path, 'wb') as f:
                for chunk in video_resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

            file_size = os.path.getsize(file_path)
            if file_size == 0:
                os.remove(file_path)
                return {'success': False, 'message': 'Downloaded file is empty'}

            return {'success': True, 'file_path': file_path, 'file_size': file_size, 'method': 'direct'}
        except Exception as e:
            return {'success': False, 'message': f'Direct download failed: {str(e)}'}

    def _download_via_tikwm(self, tiktok_id: str, video_url: str) -> Dict[str, any]:
        """Download via tikwm API when only a TikTok page URL is available"""
        try:
            resp = requests.post(TIKWM_API, data={'url': video_url, 'hd': 1}, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            if data.get('code') != 0:
                return {'success': False, 'message': f"tikwm API error: {data.get('msg', 'Unknown error')}"}

            play_url = data['data'].get('hdplay') or data['data'].get('play')
            if not play_url:
                return {'success': False, 'message': 'No download URL in tikwm response'}

            return self._download_direct_url(tiktok_id, play_url)
        except Exception as e:
            return {'success': False, 'message': f'tikwm download failed: {str(e)}'}

    def _download_via_ytdlp(self, tiktok_id: str, video_url: str) -> Dict[str, any]:
        """Fallback download method using yt-dlp"""
        file_path = os.path.join(self.download_path, f"{tiktok_id}.mp4")
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if not info:
                    return {'success': False, 'message': 'yt-dlp: Failed to extract video info'}
                ydl.download([video_url])
            
            if not os.path.exists(file_path):
                return {'success': False, 'message': 'yt-dlp: File not found after download'}
            
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                os.remove(file_path)
                return {'success': False, 'message': 'yt-dlp: Downloaded file is empty'}
            
            return {'success': True, 'file_path': file_path, 'file_size': file_size, 'method': 'yt-dlp'}
            
        except Exception as e:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return {'success': False, 'message': f'yt-dlp download failed: {str(e)}'}

    def download_video(self, tiktok_id: str, video_url: str) -> Dict[str, any]:
        """Download a single video — tries tikwm first, falls back to yt-dlp"""
        try:
            file_path = os.path.join(self.download_path, f"{tiktok_id}.mp4")
            
            # Check if file already exists
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                self.database.log_info('downloader', f'Video already exists: {tiktok_id}')
                self.database.update_video_downloaded(tiktok_id, file_path)
                return {'success': True, 'tiktok_id': tiktok_id, 'file_path': file_path, 'message': 'Video already exists'}
            
            # Route download based on URL type
            is_direct_url = video_url.startswith('https://v') or 'tiktokcdn' in video_url or 'tiktokv' in video_url
            if is_direct_url:
                # Direct CDN URL from tikwm scraper — download immediately
                result = self._download_direct_url(tiktok_id, video_url)
            else:
                # TikTok page URL — resolve via tikwm API
                result = self._download_via_tikwm(tiktok_id, video_url)
            
            if not result['success']:
                self.database.log_warning('downloader', f'Primary download failed for {tiktok_id}: {result["message"]}, trying yt-dlp')
                result = self._download_via_ytdlp(tiktok_id, video_url)
            
            if result['success']:
                if self.database.update_video_downloaded(tiktok_id, result['file_path']):
                    self.database.log_info('downloader', f"Downloaded {tiktok_id} via {result.get('method', 'unknown')} ({result['file_size']} bytes)")
                    return {'success': True, 'tiktok_id': tiktok_id, 'file_path': result['file_path'],
                            'file_size': result['file_size'], 'message': 'Download successful'}
                else:
                    os.remove(result['file_path'])
                    return {'success': False, 'tiktok_id': tiktok_id, 'message': 'Download OK but DB update failed'}
            else:
                self.database.log_error('downloader', f"All methods failed for {tiktok_id}: {result['message']}")
                return {'success': False, 'tiktok_id': tiktok_id, 'message': result['message']}
                
        except Exception as e:
            self.database.log_error('downloader', f'Unexpected error downloading {tiktok_id}: {str(e)}')
            return {'success': False, 'tiktok_id': tiktok_id, 'message': str(e)}
    
    def download_video_with_retry(self, tiktok_id: str, video_url: str) -> Dict[str, any]:
        """Download video with retry logic"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                result = self.download_video(tiktok_id, video_url)
                if result['success']:
                    return result
                
                last_error = result['message']
                self.database.log_warning('downloader', f'Download attempt {attempt + 1} failed for {tiktok_id}: {last_error}')
                
                # Wait before retry (exponential backoff)
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    import time
                    time.sleep(wait_time)
                    
            except Exception as e:
                last_error = str(e)
                self.database.log_error('downloader', f'Download attempt {attempt + 1} exception for {tiktok_id}: {last_error}')
                
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    import time
                    time.sleep(wait_time)
        
        # All retries failed
        self.database.log_error('downloader', f'All download attempts failed for {tiktok_id}: {last_error}')
        return {
            'success': False,
            'tiktok_id': tiktok_id,
            'message': f'Failed after {self.max_retries} attempts: {last_error}'
        }
    
    def download_pending_videos(self, limit: int = 50) -> Dict[str, any]:
        """Download all pending videos"""
        pending_videos = self.database.get_pending_downloads(limit)
        
        if not pending_videos:
            return {
                'success': True,
                'downloaded': 0,
                'failed': 0,
                'message': 'No pending videos to download'
            }
        
        downloaded_count = 0
        failed_count = 0
        results = []
        
        for video in pending_videos:
            result = self.download_video_with_retry(
                video['tiktok_id'], 
                video['video_url']
            )
            
            results.append(result)
            
            if result['success']:
                downloaded_count += 1
            else:
                failed_count += 1
            
            # Add delay between downloads to avoid rate limiting
            import time
            time.sleep(1)
        
        message = f'Downloaded {downloaded_count} videos, {failed_count} failed'
        self.database.log_info('downloader', message)
        
        return {
            'success': True,
            'downloaded': downloaded_count,
            'failed': failed_count,
            'results': results,
            'message': message
        }
    
    def get_download_stats(self) -> Dict[str, any]:
        """Get download statistics"""
        try:
            total_files = 0
            total_size = 0
            
            if os.path.exists(self.download_path):
                for filename in os.listdir(self.download_path):
                    if filename.endswith('.mp4'):
                        file_path = os.path.join(self.download_path, filename)
                        if os.path.isfile(file_path):
                            total_files += 1
                            total_size += os.path.getsize(file_path)
            
            # Get database stats
            db_stats = self.database.get_system_stats()
            
            return {
                'total_files': total_files,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'database_downloaded': db_stats['overall']['downloaded'],
                'download_path': self.download_path
            }
            
        except Exception as e:
            self.database.log_error('downloader', f'Failed to get download stats: {str(e)}')
            return {
                'total_files': 0,
                'total_size_mb': 0,
                'database_downloaded': 0,
                'download_path': self.download_path
            }
    
    def cleanup_old_files(self, days_old: int = 30) -> Dict[str, any]:
        """Clean up old downloaded files"""
        try:
            import time
            current_time = time.time()
            cutoff_time = current_time - (days_old * 24 * 60 * 60)
            
            deleted_count = 0
            deleted_size = 0
            
            if os.path.exists(self.download_path):
                for filename in os.listdir(self.download_path):
                    if filename.endswith('.mp4'):
                        file_path = os.path.join(self.download_path, filename)
                        if os.path.isfile(file_path):
                            file_mtime = os.path.getmtime(file_path)
                            if file_mtime < cutoff_time:
                                file_size = os.path.getsize(file_path)
                                os.remove(file_path)
                                deleted_count += 1
                                deleted_size += file_size
            
            message = f'Cleaned up {deleted_count} old files ({deleted_size / (1024*1024):.2f} MB)'
            self.database.log_info('downloader', message)
            
            return {
                'success': True,
                'deleted_count': deleted_count,
                'deleted_size_mb': round(deleted_size / (1024 * 1024), 2),
                'message': message
            }
            
        except Exception as e:
            self.database.log_error('downloader', f'Cleanup failed: {str(e)}')
            return {
                'success': False,
                'deleted_count': 0,
                'deleted_size_mb': 0,
                'message': f'Cleanup failed: {str(e)}'
            }

# Task functions for RQ
def download_video_task(tiktok_id: str, video_url: str, database_path: str = "app/database.db", download_path: str = "/videos"):
    """Task for downloading a single video"""
    database = Database(database_path)
    downloader = VideoDownloader(database, download_path)
    
    result = downloader.download_video_with_retry(tiktok_id, video_url)
    return result

def download_pending_videos_task(database_path: str = "app/database.db", download_path: str = "/videos", limit: int = 50):
    """Task for downloading all pending videos"""
    database = Database(database_path)
    downloader = VideoDownloader(database, download_path)
    
    result = downloader.download_pending_videos(limit)
    return result

def cleanup_files_task(database_path: str = "app/database.db", download_path: str = "/videos", days_old: int = 30):
    """Task for cleaning up old files"""
    database = Database(database_path)
    downloader = VideoDownloader(database, download_path)
    
    result = downloader.cleanup_old_files(days_old)
    return result

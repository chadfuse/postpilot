import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional
import json

class Database:
    def __init__(self, db_path: str = "app/database.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize database with all required tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Videos table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tiktok_id TEXT UNIQUE NOT NULL,
                    video_url TEXT NOT NULL,
                    caption TEXT,
                    author TEXT,
                    hashtags TEXT,
                    file_path TEXT,
                    downloaded BOOLEAN DEFAULT FALSE,
                    posted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Keywords table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT UNIQUE NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_scraped TIMESTAMP
                )
            ''')
            
            # Posts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL,
                    description TEXT,
                    hashtags TEXT,
                    status TEXT DEFAULT 'pending',
                    scheduled_time TIMESTAMP,
                    posted_time TIMESTAMP,
                    facebook_post_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                )
            ''')
            
            # Logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # System stats table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stat_date DATE UNIQUE NOT NULL,
                    videos_scraped INTEGER DEFAULT 0,
                    videos_downloaded INTEGER DEFAULT 0,
                    videos_posted INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def add_keyword(self, keyword: str) -> bool:
        """Add a new keyword for scraping"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT OR IGNORE INTO keywords (keyword) VALUES (?)', (keyword,))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to add keyword {keyword}: {str(e)}')
            return False
    
    def remove_keyword(self, keyword: str) -> bool:
        """Remove a keyword from scraping"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM keywords WHERE keyword = ?', (keyword,))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to remove keyword {keyword}: {str(e)}')
            return False
    
    def get_keywords(self) -> List[str]:
        """Get all active keywords"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT keyword FROM keywords WHERE active = TRUE')
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to get keywords: {str(e)}')
            return []
    
    def update_keyword_scraped_time(self, keyword: str) -> bool:
        """Update the last scraped time for a keyword"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE keywords 
                    SET last_scraped = CURRENT_TIMESTAMP 
                    WHERE keyword = ?
                ''', (keyword,))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to update keyword scraped time {keyword}: {str(e)}')
            return False
    
    def add_video(self, tiktok_id: str, video_url: str, caption: str, author: str, hashtags: List[str]) -> bool:
        """Add a new video to database"""
        try:
            hashtags_str = json.dumps(hashtags) if hashtags else '[]'
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO videos 
                    (tiktok_id, video_url, caption, author, hashtags) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (tiktok_id, video_url, caption, author, hashtags_str))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to add video {tiktok_id}: {str(e)}')
            return False
    
    def update_video_downloaded(self, tiktok_id: str, file_path: str) -> bool:
        """Mark video as downloaded and set file path"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE videos 
                    SET downloaded = TRUE, file_path = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE tiktok_id = ?
                ''', (file_path, tiktok_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to update video download status {tiktok_id}: {str(e)}')
            return False
    
    def update_video_posted(self, tiktok_id: str, facebook_post_id: str) -> bool:
        """Mark video as posted"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE videos 
                    SET posted = TRUE, updated_at = CURRENT_TIMESTAMP 
                    WHERE tiktok_id = ?
                ''', (tiktok_id,))
                videos_updated = cursor.rowcount
                
                cursor.execute('''
                    UPDATE posts 
                    SET status = 'posted', posted_time = CURRENT_TIMESTAMP, facebook_post_id = ?
                    WHERE video_id = (SELECT id FROM videos WHERE tiktok_id = ?)
                ''', (facebook_post_id, tiktok_id))
                
                conn.commit()
                return videos_updated > 0
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to update video post status {tiktok_id}: {str(e)}')
            return False
    
    def get_videos(self, downloaded: bool = None, posted: bool = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get videos with optional filters"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                conditions = []
                params = []
                if downloaded is not None:
                    conditions.append('downloaded = ?')
                    params.append(1 if downloaded else 0)
                if posted is not None:
                    conditions.append('posted = ?')
                    params.append(1 if posted else 0)
                where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
                params.extend([limit, offset])
                cursor.execute(f'''
                    SELECT tiktok_id, video_url, file_path, caption, author, hashtags,
                           downloaded, posted, created_at, updated_at
                    FROM videos
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                ''', params)
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'tiktok_id': row[0],
                        'video_url': row[1],
                        'file_path': row[2],
                        'caption': row[3],
                        'author': row[4],
                        'hashtags': json.loads(row[5]) if row[5] else [],
                        'downloaded': bool(row[6]),
                        'posted': bool(row[7]),
                        'created_at': row[8],
                        'updated_at': row[9]
                    })
                return results
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to get videos: {str(e)}')
            return []

    def get_pending_downloads(self, limit: int = 50) -> List[Dict]:
        """Get videos that need to be downloaded"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT tiktok_id, video_url, caption, author, hashtags
                    FROM videos 
                    WHERE downloaded = FALSE 
                    ORDER BY created_at ASC 
                    LIMIT ?
                ''', (limit,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'tiktok_id': row[0],
                        'video_url': row[1],
                        'caption': row[2],
                        'author': row[3],
                        'hashtags': json.loads(row[4]) if row[4] else []
                    })
                return results
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to get pending downloads: {str(e)}')
            return []
    
    def get_pending_posts(self, limit: int = 15) -> List[Dict]:
        """Get videos ready for posting"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT v.tiktok_id, v.file_path, v.caption, v.author, v.hashtags
                    FROM videos v
                    WHERE v.downloaded = TRUE AND v.posted = FALSE
                    ORDER BY v.created_at ASC 
                    LIMIT ?
                ''', (limit,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'tiktok_id': row[0],
                        'file_path': row[1],
                        'caption': row[2],
                        'author': row[3],
                        'hashtags': json.loads(row[4]) if row[4] else []
                    })
                return results
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to get pending posts: {str(e)}')
            return []
    
    def get_system_stats(self) -> Dict:
        """Get system statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Today's stats
                today = datetime.now().date()
                cursor.execute('''
                    SELECT COALESCE(videos_scraped, 0), COALESCE(videos_downloaded, 0), COALESCE(videos_posted, 0)
                    FROM system_stats 
                    WHERE stat_date = ?
                ''', (today,))
                today_stats = cursor.fetchone() or (0, 0, 0)
                
                # Overall stats
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_videos,
                        COUNT(CASE WHEN downloaded = TRUE THEN 1 END) as downloaded_count,
                        COUNT(CASE WHEN posted = TRUE THEN 1 END) as posted_count
                    FROM videos
                ''')
                overall_stats = cursor.fetchone()
                
                cursor.execute('SELECT COUNT(*) FROM keywords WHERE active = TRUE')
                keyword_count = cursor.fetchone()[0]
                
                return {
                    'today': {
                        'scraped': today_stats[0],
                        'downloaded': today_stats[1],
                        'posted': today_stats[2]
                    },
                    'overall': {
                        'total_videos': overall_stats[0],
                        'downloaded': overall_stats[1],
                        'posted': overall_stats[2],
                        'keywords': keyword_count
                    }
                }
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to get system stats: {str(e)}')
            return {'today': {'scraped': 0, 'downloaded': 0, 'posted': 0}, 'overall': {'total_videos': 0, 'downloaded': 0, 'posted': 0, 'keywords': 0}}
    
    def update_daily_stats(self, scraped: int = 0, downloaded: int = 0, posted: int = 0):
        """Update daily statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                today = datetime.now().date()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO system_stats 
                    (stat_date, videos_scraped, videos_downloaded, videos_posted, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (today, scraped, downloaded, posted))
                
                conn.commit()
        except sqlite3.Error as e:
            self.log_error('database', f'Failed to update daily stats: {str(e)}')
    
    def log_info(self, component: str, message: str, details: str = None):
        """Log info message"""
        self._log('info', component, message, details)
    
    def log_error(self, component: str, message: str, details: str = None):
        """Log error message"""
        self._log('error', component, message, details)
    
    def log_warning(self, component: str, message: str, details: str = None):
        """Log warning message"""
        self._log('warning', component, message, details)
    
    def _log(self, log_type: str, component: str, message: str, details: str = None):
        """Internal logging method"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO logs (type, message, details)
                    VALUES (?, ?, ?)
                ''', (f'{log_type}:{component}', message, details))
                conn.commit()
        except sqlite3.Error:
            pass  # Avoid infinite recursion if logging fails
    
    def get_recent_logs(self, limit: int = 100) -> List[Dict]:
        """Get recent log entries"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT type, message, details, created_at
                    FROM logs 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (limit,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'type': row[0],
                        'message': row[1],
                        'details': row[2],
                        'created_at': row[3]
                    })
                return results
        except sqlite3.Error as e:
            return []

import os
import time
import re
import requests
from typing import List, Dict, Optional
from datetime import datetime
from .database import Database

TIKWM_SEARCH_API = "https://www.tikwm.com/api/feed/search"

class TikTokScraper:
    def __init__(self, database: Database, max_videos_per_keyword: int = 50):
        self.database = database
        self.max_videos_per_keyword = max_videos_per_keyword

    def scrape_videos_by_keyword(self, keyword: str, count: int = None) -> List[Dict]:
        """Scrape TikTok videos by keyword using tikwm.com search API"""
        if count is None:
            count = self.max_videos_per_keyword

        videos = []
        cursor = 0
        batch_size = min(count, 20)

        try:
            while len(videos) < count:
                resp = requests.get(TIKWM_SEARCH_API, params={
                    'keywords': keyword,
                    'count': batch_size,
                    'cursor': cursor,
                    'HD': 1
                }, timeout=20)
                resp.raise_for_status()
                data = resp.json()

                if data.get('code') != 0:
                    self.database.log_error('scraper', f'tikwm search error for {keyword}: {data.get("msg")}')
                    break

                batch = data.get('data', {}).get('videos', [])
                if not batch:
                    break

                for item in batch:
                    video_data = self._extract_video_data(item, keyword)
                    if not video_data:
                        continue

                    added = self.database.add_video(
                        tiktok_id=video_data['tiktok_id'],
                        video_url=video_data['video_url'],
                        caption=video_data['caption'],
                        author=video_data['author'],
                        hashtags=video_data['hashtags']
                    )
                    if added:
                        videos.append(video_data)

                    if len(videos) >= count:
                        break

                cursor += len(batch)
                if len(batch) < batch_size:
                    break
                time.sleep(1)

            self.database.log_info('scraper', f'Scraped {len(videos)} new videos for keyword: {keyword}')
            return videos

        except Exception as e:
            self.database.log_error('scraper', f'Failed to scrape keyword {keyword}: {str(e)}')
            return []

    def _extract_video_data(self, item: Dict, keyword: str) -> Optional[Dict]:
        """Extract and normalize video data from tikwm search result"""
        try:
            tiktok_id = str(item.get('video_id', ''))
            if not tiktok_id:
                return None

            # Use direct play URL — no watermark, ready for download
            video_url = item.get('play', '') or item.get('hdplay', '')
            if not video_url:
                return None

            caption = item.get('title', '')
            author = item.get('author', {}).get('unique_id', '') or item.get('author', {}).get('nickname', '')

            # Extract hashtags from caption
            hashtags = re.findall(r'#(\w+)', caption)
            if keyword not in hashtags:
                hashtags.insert(0, keyword)

            return {
                'tiktok_id': tiktok_id,
                'video_url': video_url,
                'caption': caption,
                'author': author,
                'hashtags': hashtags,
                'scraped_at': datetime.now().isoformat()
            }
        except Exception as e:
            self.database.log_error('scraper', f'Failed to extract video data: {str(e)}')
            return None

    def scrape_all_keywords(self) -> Dict[str, int]:
        """Scrape videos for all active keywords"""
        keywords = self.database.get_keywords()
        results = {}

        for keyword in keywords:
            try:
                videos = self.scrape_videos_by_keyword(keyword)
                results[keyword] = len(videos)
                self.database.update_keyword_scraped_time(keyword)
                time.sleep(2)
            except Exception as e:
                self.database.log_error('scraper', f'Failed to scrape keyword {keyword}: {str(e)}')
                results[keyword] = 0

        return results

    def extract_hashtags_from_caption(self, caption: str) -> List[str]:
        """Extract hashtags from caption text"""
        if not caption:
            return []
        return re.findall(r'#(\w+)', caption)


# Task queue functions (synchronous, for RQ workers)
def scrape_keyword_task(keyword: str, database_path: str = "app/database.db"):
    """Task for scraping a single keyword"""
    database = Database(database_path)
    scraper = TikTokScraper(database)
    try:
        videos = scraper.scrape_videos_by_keyword(keyword)
        return {
            'success': True,
            'keyword': keyword,
            'videos_found': len(videos),
            'message': f'Scraped {len(videos)} videos for {keyword}'
        }
    except Exception as e:
        database.log_error('scraper', f'Task failed for keyword {keyword}: {str(e)}')
        return {'success': False, 'keyword': keyword, 'videos_found': 0, 'message': str(e)}


def scrape_all_keywords_task(database_path: str = "app/database.db"):
    """Task for scraping all keywords"""
    database = Database(database_path)
    scraper = TikTokScraper(database)
    try:
        results = scraper.scrape_all_keywords()
        total_videos = sum(results.values())
        database.log_info('scraper', f'Batch scraping completed: {total_videos} videos from {len(results)} keywords')
        return {
            'success': True,
            'total_videos': total_videos,
            'results': results,
            'message': f'Scraped {total_videos} videos from {len(results)} keywords'
        }
    except Exception as e:
        database.log_error('scraper', f'Batch scraping failed: {str(e)}')
        return {'success': False, 'total_videos': 0, 'results': {}, 'message': str(e)}


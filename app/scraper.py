import os
import time
import re
import random
import requests
from typing import List, Dict, Optional
from datetime import datetime
from .database import Database

TIKWM_SEARCH_API = "https://www.tikwm.com/api/feed/search"

class TikTokScraper:
    def __init__(self, database: Database, max_videos_per_keyword: int = 100):
        self.database = database
        self.max_videos_per_keyword = max_videos_per_keyword
        self.trending_keywords = [
            "viral", "trending", "fyp", "foryou", "tiktok", "viralvideo",
            "dance", "music", "comedy", "pets", "food", "travel", "fashion",
            "fitness", "art", "diy", "tech", "gaming", "sports", "nature"
        ]

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

            # Verify a playable URL exists (needed to confirm video is valid)
            play_url = item.get('play', '') or item.get('hdplay', '')
            if not play_url:
                return None

            caption = item.get('title', '')
            author = item.get('author', {}).get('unique_id', '') or item.get('author', {}).get('nickname', '')

            # Store a permanent TikTok page URL instead of the expiring CDN URL.
            # The downloader will resolve a fresh CDN URL at download time.
            video_url = f"https://www.tiktok.com/@{author}/video/{tiktok_id}"

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

    def scrape_trending_keywords(self, limit: int = 5) -> Dict[str, int]:
        """Scrape trending hashtags for fresh content"""
        selected = random.sample(self.trending_keywords, min(limit, len(self.trending_keywords)))
        results = {}
        
        for keyword in selected:
            try:
                # Use lower count for trending to avoid overwhelming
                videos = self.scrape_videos_by_keyword(keyword, count=30)
                results[f"trending_{keyword}"] = len(videos)
                time.sleep(1)  # Rate limiting
            except Exception as e:
                self.database.log_error('scraper', f'Failed to scrape trending {keyword}: {str(e)}')
                results[f"trending_{keyword}"] = 0
        
        return results
    
    def scrape_related_for_keyword(self, base_keyword: str, limit: int = 3) -> Dict[str, int]:
        """Scrape keywords related to a specific user keyword"""
        # Smart related keywords based on the base keyword
        related_map = {
            'slingshot': ['shooting', 'aim', 'target', 'outdoor', 'hunting', 'weapons', 'precision'],
            'outdoor': ['nature', 'adventure', 'camping', 'hiking', 'wildlife', 'exploration', 'survival'],
            'diy': ['craft', 'homemade', 'tutorial', 'howto', 'project', 'build', 'create'],
            'fitness': ['workout', 'exercise', 'gym', 'training', 'health', 'strength', 'cardio'],
            'food': ['cooking', 'recipe', 'chef', 'kitchen', 'meal', 'baking', 'restaurant'],
            'travel': ['adventure', 'vacation', 'trip', 'explore', 'journey', 'tourism', 'wanderlust'],
            'default': ['viral', 'trending', 'popular', 'amazing', 'cool', 'awesome', 'best']
        }
        
        # Get related keywords or use defaults
        base_lower = base_keyword.lower()
        related = related_map.get(base_lower, related_map['default'])
        selected = related[:limit]
        
        results = {}
        for related_keyword in selected:
            try:
                # Combine base keyword with related for better relevance
                search_term = f"{base_keyword} {related_keyword}"
                videos = self.scrape_videos_by_keyword(search_term, count=30)
                results[f"related_{base_keyword}_{related_keyword}"] = len(videos)
                time.sleep(1)
            except Exception as e:
                self.database.log_error('scraper', f'Failed to scrape related {base_keyword}_{related_keyword}: {str(e)}')
                results[f"related_{base_keyword}_{related_keyword}"] = 0
        
        return results
    
    def scrape_keyword_by_time(self, keyword: str, limit: int = 2) -> Dict[str, int]:
        """Scrape time-based variations of a specific keyword"""
        time_modifiers = ['2024', 'this week', 'new', 'latest', 'recent']
        selected = time_modifiers[:limit]
        
        results = {}
        for modifier in selected:
            try:
                search_term = f"{keyword} {modifier}"
                videos = self.scrape_videos_by_keyword(search_term, count=25)
                results[f"time_{keyword}_{modifier.replace(' ', '_')}"] = len(videos)
                time.sleep(1)
            except Exception as e:
                self.database.log_error('scraper', f'Failed to scrape time {keyword}_{modifier}: {str(e)}')
                results[f"time_{keyword}_{modifier.replace(' ', '_')}"] = 0
        
        return results
    
    def scrape_by_time_range(self, limit: int = 3) -> Dict[str, int]:
        """Scrape older videos by using time-based modifiers"""
        time_modifiers = ['last week', 'yesterday', 'this month', '2024', 'popular']
        selected = random.sample(time_modifiers, min(limit, len(time_modifiers)))
        results = {}
        
        for modifier in selected:
            try:
                # Combine with a trending keyword
                base_keyword = random.choice(['viral', 'trending', 'fyp'])
                search_term = f"{base_keyword} {modifier}"
                videos = self.scrape_videos_by_keyword(search_term, count=20)
                results[f"time_{modifier}"] = len(videos)
                time.sleep(1)
            except Exception as e:
                self.database.log_error('scraper', f'Failed to scrape time-based {modifier}: {str(e)}')
                results[f"time_{modifier}"] = 0
        
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


def unlimited_scraping_task(database_path: str = "app/database.db"):
    """Smart unlimited scraping centered around user keywords"""
    database = Database(database_path)
    scraper = TikTokScraper(database)
    try:
        total_videos = 0
        results = {}
        
        # Get user keywords - this is our foundation
        user_keywords = database.get_keywords()
        if not user_keywords:
            return {
                'success': False, 
                'total_videos': 0, 
                'results': {}, 
                'message': 'No keywords configured. Please add keywords first.'
            }
        
        # Strategy 1: Deep scrape user keywords (higher count)
        for keyword in user_keywords:
            try:
                # Scrape more videos per user keyword (100 instead of default 50)
                videos = scraper.scrape_videos_by_keyword(keyword, count=100)
                results[f"user_{keyword}"] = len(videos)
                total_videos += len(videos)
                time.sleep(1)  # Rate limiting
            except Exception as e:
                database.log_error('scraper', f'Failed to deep scrape {keyword}: {str(e)}')
                results[f"user_{keyword}"] = 0
        
        # Strategy 2: Expand around user keywords (only if still need content)
        if total_videos < len(user_keywords) * 20:  # If less than 20 videos per keyword
            for base_keyword in user_keywords[:3]:  # Limit to top 3 keywords
                try:
                    # Find related keywords based on user's interests
                    related_results = scraper.scrape_related_for_keyword(base_keyword, limit=3)
                    results.update(related_results)
                    total_videos += sum(related_results.values())
                except Exception as e:
                    database.log_error('scraper', f'Failed to expand {base_keyword}: {str(e)}')
        
        # Strategy 3: Time-based variations of user keywords
        if total_videos < len(user_keywords) * 30:
            for keyword in user_keywords[:2]:  # Limit to top 2 keywords
                try:
                    time_results = scraper.scrape_keyword_by_time(keyword, limit=2)
                    results.update(time_results)
                    total_videos += sum(time_results.values())
                except Exception as e:
                    database.log_error('scraper', f'Failed time variation for {keyword}: {str(e)}')
        
        database.log_info('scraper', f'Smart unlimited scraping: {total_videos} videos for {len(user_keywords)} user keywords')
        return {
            'success': True,
            'total_videos': total_videos,
            'results': results,
            'message': f'Smart scraping: {total_videos} videos centered on your {len(user_keywords)} keywords'
        }
    except Exception as e:
        database.log_error('scraper', f'Smart unlimited scraping failed: {str(e)}')
        return {'success': False, 'total_videos': 0, 'results': {}, 'message': str(e)}


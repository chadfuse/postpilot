import os
import requests
import json
from typing import Dict, List, Optional
from datetime import datetime
from .database import Database

class FacebookPoster:
    def __init__(self, database: Database, page_id: str, access_token: str, max_retries: int = 3):
        self.database = database
        self.page_id = page_id
        self.access_token = access_token
        self.max_retries = max_retries
        self.api_base_url = "https://graph.facebook.com/v18.0"
        
        # Verify credentials
        self._verify_credentials()
    
    def _verify_credentials(self):
        """Verify Facebook API credentials"""
        try:
            url = f"{self.api_base_url}/me"
            params = {
                'access_token': self.access_token,
                'fields': 'id,name'
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                user_info = response.json()
                self.database.log_info('poster', f'Facebook credentials verified for user: {user_info.get("name", "Unknown")}')
            else:
                self.database.log_error('poster', f'Facebook credential verification failed: {response.status_code}')
                
        except Exception as e:
            self.database.log_error('poster', f'Facebook credential verification error: {str(e)}')
    
    def generate_post_description(self, caption: str, author: str, hashtags: List[str]) -> str:
        """Generate Facebook post description from TikTok data"""
        # Clean and format caption
        description = ""
        
        # Add original caption if exists
        if caption and caption.strip():
            # Remove TikTok-specific elements
            clean_caption = caption.strip()
            clean_caption = clean_caption.replace('#', ' #')  # Add space before hashtags
            description += f"{clean_caption}\n\n"
        
        # Add credit line
        if author:
            description += f"Credit: @{author} \n\n"
        else:
            description += "Credit: creator\n\n"
        
        # Add relevant hashtags
        if hashtags:
            # Limit hashtags and format for Facebook
            facebook_hashtags = hashtags[:10]  # Limit to 10 hashtags
            hashtag_string = " ".join([f"#{tag}" for tag in facebook_hashtags])
            description += hashtag_string
        
        # Add generic hashtags if none provided
        if not hashtags:
            description += "#TikTok #Viral #ContentCreator #SocialMedia"
        
        # Ensure description is within Facebook limits (8000 characters)
        if len(description) > 8000:
            description = description[:7970] + "..."
        
        return description.strip()
    
    def upload_video_to_facebook(self, video_path: str, description: str) -> Dict[str, any]:
        """Upload video to Facebook page"""
        try:
            # Check if video file exists
            if not os.path.exists(video_path):
                raise Exception(f"Video file not found: {video_path}")
            
            # Check file size (Facebook limit is 4GB for pages)
            file_size = os.path.getsize(video_path)
            if file_size > 4 * 1024 * 1024 * 1024:  # 4GB
                raise Exception(f"Video file too large: {file_size / (1024*1024*1024):.2f}GB (limit: 4GB)")
            
            # Start video upload session
            upload_url = f"{self.api_base_url}/{self.page_id}/videos"
            
            # Prepare upload data
            data = {
                'access_token': self.access_token,
                'description': description,
                'published': True,  # Publish immediately
            }
            
            # Upload video file
            with open(video_path, 'rb') as video_file:
                files = {'source': video_file}
                
                response = requests.post(
                    upload_url,
                    data=data,
                    files=files,
                    timeout=300  # 5 minutes timeout for video upload
                )
            
            if response.status_code == 200:
                result = response.json()
                
                if 'id' in result:
                    facebook_post_id = result['id']
                    self.database.log_info('poster', f'Video uploaded successfully: {facebook_post_id}')
                    
                    return {
                        'success': True,
                        'facebook_post_id': facebook_post_id,
                        'message': 'Video uploaded successfully'
                    }
                else:
                    error_msg = result.get('error', {}).get('message', 'Unknown error')
                    raise Exception(f"Facebook API error: {error_msg}")
            else:
                error_info = response.json() if response.content else {}
                error_msg = error_info.get('error', {}).get('message', f'HTTP {response.status_code}')
                raise Exception(f"Facebook upload failed: {error_msg}")
                
        except Exception as e:
            error_msg = str(e)
            self.database.log_error('poster', f'Video upload failed: {error_msg}')
            return {
                'success': False,
                'message': f'Upload failed: {error_msg}'
            }
    
    def post_video_with_retry(self, tiktok_id: str, video_path: str, caption: str, author: str, hashtags: List[str]) -> Dict[str, any]:
        """Post video with retry logic"""
        # Generate post description
        description = self.generate_post_description(caption, author, hashtags)
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                result = self.upload_video_to_facebook(video_path, description)
                
                if result['success']:
                    # Update database with Facebook post ID
                    if self.database.update_video_posted(tiktok_id, result['facebook_post_id']):
                        self.database.log_info('poster', f'Successfully posted video {tiktok_id} to Facebook')
                        # Delete local video file to free disk space (DB record kept for dedup)
                        try:
                            if video_path and os.path.exists(video_path):
                                os.remove(video_path)
                                self.database.log_info('poster', f'Deleted local file after posting: {video_path}')
                        except Exception as del_err:
                            self.database.log_warning('poster', f'Could not delete file {video_path}: {del_err}')
                        return {
                            'success': True,
                            'tiktok_id': tiktok_id,
                            'facebook_post_id': result['facebook_post_id'],
                            'message': 'Video posted successfully'
                        }
                    else:
                        return {
                            'success': False,
                            'tiktok_id': tiktok_id,
                            'message': 'Post successful but failed to update database'
                        }
                else:
                    last_error = result['message']
                    self.database.log_warning('poster', f'Post attempt {attempt + 1} failed for {tiktok_id}: {last_error}')
                
                # Wait before retry (exponential backoff)
                if attempt < self.max_retries - 1:
                    import time
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    
            except Exception as e:
                last_error = str(e)
                self.database.log_error('poster', f'Post attempt {attempt + 1} exception for {tiktok_id}: {last_error}')
                
                if attempt < self.max_retries - 1:
                    import time
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
        
        # All retries failed
        self.database.log_error('poster', f'All post attempts failed for {tiktok_id}: {last_error}')
        return {
            'success': False,
            'tiktok_id': tiktok_id,
            'message': f'Failed after {self.max_retries} attempts: {last_error}'
        }
    
    def post_pending_videos(self, limit: int = 15) -> Dict[str, any]:
        """Post all pending videos"""
        pending_videos = self.database.get_pending_posts(limit)
        
        if not pending_videos:
            return {
                'success': True,
                'posted': 0,
                'failed': 0,
                'message': 'No pending videos to post'
            }
        
        posted_count = 0
        failed_count = 0
        results = []
        
        for video in pending_videos:
            result = self.post_video_with_retry(
                tiktok_id=video['tiktok_id'],
                video_path=video['file_path'],
                caption=video['caption'],
                author=video['author'],
                hashtags=video['hashtags']
            )
            
            results.append(result)
            
            if result['success']:
                posted_count += 1
            else:
                failed_count += 1
            
            # Add delay between posts to avoid rate limiting
            import time
            time.sleep(30)  # 30 seconds between posts
        
        message = f'Posted {posted_count} videos, {failed_count} failed'
        self.database.log_info('poster', message)
        
        return {
            'success': True,
            'posted': posted_count,
            'failed': failed_count,
            'results': results,
            'message': message
        }
    
    def get_facebook_post_info(self, post_id: str) -> Dict[str, any]:
        """Get information about a Facebook post"""
        try:
            url = f"{self.api_base_url}/{post_id}"
            params = {
                'access_token': self.access_token,
                'fields': 'id,created_time,description,source,likes.summary(true),comments.summary(true),shares'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            else:
                return {
                    'success': False,
                    'message': f'Failed to get post info: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Error getting post info: {str(e)}'
            }
    
    def get_page_stats(self) -> Dict[str, any]:
        """Get Facebook page statistics"""
        try:
            url = f"{self.api_base_url}/{self.page_id}"
            params = {
                'access_token': self.access_token,
                'fields': 'fan_count,talking_about_count,username,name'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                page_data = response.json()
                return {
                    'success': True,
                    'page_name': page_data.get('name', 'Unknown'),
                    'username': page_data.get('username', ''),
                    'followers': page_data.get('fan_count', 0),
                    'talking_about': page_data.get('talking_about_count', 0)
                }
            else:
                self.database.log_error('poster', f'Failed to get page stats: {response.status_code}')
                return {
                    'success': False,
                    'message': f'Failed to get page stats: {response.status_code}'
                }
                
        except Exception as e:
            self.database.log_error('poster', f'Error getting page stats: {str(e)}')
            return {
                'success': False,
                'message': f'Error getting page stats: {str(e)}'
            }

# Task functions for RQ
def post_video_task(tiktok_id: str, video_path: str, caption: str, author: str, hashtags: List[str], 
                   page_id: str, access_token: str, database_path: str = "app/database.db"):
    """Task for posting a single video"""
    database = Database(database_path)
    poster = FacebookPoster(database, page_id, access_token)
    
    result = poster.post_video_with_retry(tiktok_id, video_path, caption, author, hashtags)
    return result

def post_pending_videos_task(page_id: str, access_token: str, database_path: str = "app/database.db", limit: int = 15):
    """Task for posting all pending videos"""
    database = Database(database_path)
    poster = FacebookPoster(database, page_id, access_token)
    
    result = poster.post_pending_videos(limit)
    return result

def get_facebook_stats_task(page_id: str, access_token: str, database_path: str = "app/database.db"):
    """Task for getting Facebook page statistics"""
    database = Database(database_path)
    poster = FacebookPoster(database, page_id, access_token)
    
    result = poster.get_page_stats()
    return result

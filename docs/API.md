# API Documentation

This document provides comprehensive API documentation for the TikTok Video Collector system.

## Base URL

```
http://localhost:8000 (development)
https://your-app.onrender.com (production)
```

## Authentication

Currently, the API does not require authentication. For production use, consider implementing API keys or OAuth.

## Response Format

All responses follow this format:

```json
{
  "success": true|false,
  "data": {}, // Optional
  "message": "string", // Optional
  "error": "string" // Optional on error
}
```

## Health & Status

### GET /health

Check system health status.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### GET /stats

Get comprehensive system statistics.

**Response:**
```json
{
  "success": true,
  "database": {
    "today": {
      "scraped": 25,
      "downloaded": 20,
      "posted": 15
    },
    "overall": {
      "total_videos": 1500,
      "downloaded": 1200,
      "posted": 800,
      "keywords": 10
    }
  },
  "config": {
    "MAX_POSTS_PER_DAY": 15,
    "SCRAPE_INTERVAL": 30,
    "POST_INTERVAL": 60
  },
  "queue": {
    "pending_jobs": 5,
    "failed_jobs": 1,
    "scheduled_jobs": 2,
    "started_jobs": 1
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## Keywords Management

### GET /keywords

Get all active keywords.

**Response:**
```json
{
  "success": true,
  "keywords": ["funny", "dance", "pets", "cooking"],
  "count": 4
}
```

### POST /keywords

Add a new keyword for scraping.

**Request Body:**
```json
{
  "keyword": "comedy"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Keyword 'comedy' added successfully"
}
```

**Error Response:**
```json
{
  "success": false,
  "message": "Keyword already exists or failed to add"
}
```

### DELETE /keywords/{keyword}

Remove a keyword from scraping.

**Path Parameters:**
- `keyword` (string): The keyword to remove

**Response:**
```json
{
  "success": true,
  "message": "Keyword 'comedy' removed successfully"
}
```

## Videos Management

### GET /videos

Get videos with optional filters.

**Query Parameters:**
- `downloaded` (boolean, optional): Filter by download status
- `posted` (boolean, optional): Filter by post status
- `limit` (integer, optional): Maximum number of results (default: 50, max: 100)
- `offset` (integer, optional): Number of results to skip (default: 0)

**Response:**
```json
{
  "success": true,
  "videos": [
    {
      "id": 1,
      "tiktok_id": "1234567890",
      "video_url": "https://v.tiktok.com/...",
      "caption": "Amazing video!",
      "author": "user123",
      "hashtags": ["funny", "viral"],
      "file_path": "/videos/1234567890.mp4",
      "downloaded": true,
      "posted": false,
      "created_at": "2024-01-01T12:00:00Z"
    }
  ],
  "count": 1,
  "filters": {
    "downloaded": true,
    "posted": false,
    "limit": 50,
    "offset": 0
  }
}
```

### GET /videos/pending-download

Get videos pending download.

**Query Parameters:**
- `limit` (integer, optional): Maximum number of results (default: 50, max: 100)

**Response:**
```json
{
  "success": true,
  "videos": [
    {
      "tiktok_id": "1234567890",
      "video_url": "https://v.tiktok.com/...",
      "caption": "Amazing video!",
      "author": "user123",
      "hashtags": ["funny", "viral"]
    }
  ],
  "count": 1
}
```

### GET /videos/pending-post

Get videos pending posting.

**Query Parameters:**
- `limit` (integer, optional): Maximum number of results (default: 15, max: 50)

**Response:**
```json
{
  "success": true,
  "videos": [
    {
      "tiktok_id": "1234567890",
      "file_path": "/videos/1234567890.mp4",
      "caption": "Amazing video!",
      "author": "user123",
      "hashtags": ["funny", "viral"]
    }
  ],
  "count": 1
}
```

## Task Management

### POST /tasks/scrape-keyword/{keyword}

Start scraping task for a single keyword.

**Path Parameters:**
- `keyword` (string): The keyword to scrape

**Response:**
```json
{
  "success": true,
  "job_id": "abc123def456",
  "message": "Scraping task queued for keyword: funny"
}
```

### POST /tasks/scrape-all

Start scraping task for all keywords.

**Response:**
```json
{
  "success": true,
  "job_id": "abc123def456",
  "message": "Scraping task queued for all keywords"
}
```

### POST /tasks/download-pending

Start download task for pending videos.

**Query Parameters:**
- `limit` (integer, optional): Maximum videos to download (default: 50, max: 100)

**Response:**
```json
{
  "success": true,
  "job_id": "abc123def456",
  "message": "Download task queued for 50 pending videos"
}
```

### POST /tasks/post-pending

Start posting task for pending videos.

**Query Parameters:**
- `limit` (integer, optional): Maximum videos to post (default: 15, max: 30)

**Response:**
```json
{
  "success": true,
  "job_id": "abc123def456",
  "message": "Posting task queued for 15 pending videos"
}
```

### POST /tasks/cleanup

Start cleanup task for old files.

**Query Parameters:**
- `days_old` (integer, optional): Age threshold in days (default: 30, min: 1)

**Response:**
```json
{
  "success": true,
  "job_id": "abc123def456",
  "message": "Cleanup task queued for files older than 30 days"
}
```

## Manual Actions

### POST /actions/download-video/{tiktok_id}

Manually download a specific video.

**Path Parameters:**
- `tiktok_id` (string): The TikTok video ID to download

**Response:**
```json
{
  "success": true,
  "message": "Manual download initiated for 1234567890",
  "note": "This endpoint needs implementation to get video URL from database"
}
```

### POST /actions/post-video/{tiktok_id}

Manually post a specific video.

**Path Parameters:**
- `tiktok_id` (string): The TikTok video ID to post

**Request Body:**
```json
{
  "description": "Custom description (optional)",
  "hashtags": ["custom", "hashtags"] // Optional
}
```

**Response:**
```json
{
  "success": true,
  "message": "Manual posting initiated for 1234567890",
  "note": "This endpoint needs implementation to get video details from database"
}
```

## Configuration Management

### GET /config

Get system configuration.

**Response:**
```json
{
  "success": true,
  "config": {
    "MAX_POSTS_PER_DAY": 15,
    "SCRAPE_INTERVAL": 30,
    "POST_INTERVAL": 60,
    "MAX_VIDEOS_PER_KEYWORD": 50,
    "MAX_DOWNLOAD_RETRIES": 3,
    "MAX_POST_RETRIES": 3
  }
}
```

### PUT /config

Update system configuration.

**Request Body:**
```json
{
  "max_posts_per_day": 20,
  "scrape_interval": 45,
  "post_interval": 90
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration updated successfully",
  "updates": {
    "MAX_POSTS_PER_DAY": 20,
    "SCRAPE_INTERVAL": 45,
    "POST_INTERVAL": 90
  }
}
```

## Facebook Integration

### GET /facebook/stats

Get Facebook page statistics.

**Response:**
```json
{
  "success": true,
  "page_name": "My Awesome Page",
  "username": "myawesomepage",
  "followers": 15000,
  "talking_about": 250
}
```

**Error Response:**
```json
{
  "success": false,
  "message": "Facebook credentials not configured"
}
```

## Logs

### GET /logs

Get recent system logs.

**Query Parameters:**
- `limit` (integer, optional): Number of logs to return (default: 100, max: 500)

**Response:**
```json
{
  "success": true,
  "logs": [
    {
      "type": "info:scraper",
      "message": "Scraping completed for keyword: funny",
      "details": "Videos found: 25, Duration: 45.2s",
      "created_at": "2024-01-01T12:00:00Z"
    },
    {
      "type": "error:downloader",
      "message": "Download failed for video: 1234567890",
      "details": "Network timeout after 30 seconds",
      "created_at": "2024-01-01T11:55:00Z"
    }
  ],
  "count": 2
}
```

## Error Codes

| Status Code | Description | Example |
|-------------|-------------|---------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Invalid input data |
| 404 | Not Found | Resource not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error occurred |
| 503 | Service Unavailable | Redis/RQ not available |

## Rate Limiting

The API implements rate limiting to prevent abuse:

- **General Requests**: 100 requests per minute
- **Task Creation**: 10 tasks per minute
- **Configuration Changes**: 5 updates per minute

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## WebSocket Support (Future)

Real-time updates via WebSocket will be available in future versions:

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/ws');

// Receive real-time updates
ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('Update:', data);
};
```

## SDK Examples

### Python

```python
import requests

base_url = "http://localhost:8000"

# Get system stats
response = requests.get(f"{base_url}/stats")
stats = response.json()

# Add keyword
response = requests.post(
    f"{base_url}/keywords",
    json={"keyword": "comedy"}
)

# Start scraping
response = requests.post(f"{base_url}/tasks/scrape-all")
```

### JavaScript

```javascript
const baseUrl = 'http://localhost:8000';

// Get system stats
async function getStats() {
  const response = await fetch(`${baseUrl}/stats`);
  return await response.json();
}

// Add keyword
async function addKeyword(keyword) {
  const response = await fetch(`${baseUrl}/keywords`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword })
  });
  return await response.json();
}

// Start scraping
async function startScraping() {
  const response = await fetch(`${baseUrl}/tasks/scrape-all`, {
    method: 'POST'
  });
  return await response.json();
}
```

### cURL

```bash
# Get health status
curl http://localhost:8000/health

# Get system stats
curl http://localhost:8000/stats

# Add keyword
curl -X POST http://localhost:8000/keywords \
  -H "Content-Type: application/json" \
  -d '{"keyword": "comedy"}'

# Start scraping
curl -X POST http://localhost:8000/tasks/scrape-all
```

## Testing

### Health Check

```bash
curl -f http://localhost:8000/health
```

### API Test Script

```python
#!/usr/bin/env python3
import requests
import json

base_url = "http://localhost:8000"

def test_api():
    # Test health
    health = requests.get(f"{base_url}/health")
    print("Health:", health.json())
    
    # Test stats
    stats = requests.get(f"{base_url}/stats")
    print("Stats:", stats.json())
    
    # Test keywords
    keywords = requests.get(f"{base_url}/keywords")
    print("Keywords:", keywords.json())

if __name__ == "__main__":
    test_api()
```

## Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   - Ensure Redis server is running
   - Check REDIS_URL environment variable

2. **Facebook API Errors**
   - Verify access token validity
   - Check page permissions

3. **Database Errors**
   - Check database file permissions
   - Ensure SQLite is properly installed

### Debug Mode

Enable debug logging by setting `DEBUG=true` environment variable.

### Log Locations

- **System Logs**: `/logs/system.log`
- **Error Logs**: `/logs/errors.log`
- **Debug Logs**: `/logs/debug.log` (debug mode only)

---

For additional support, check the system logs or create an issue on GitHub.

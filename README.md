# TikTok Video Collector and Facebook Auto Publisher

A fully automated system for collecting TikTok videos and posting them to Facebook, built with Python and deployed on Render's free tier.

## 🚀 Features

- **Automated TikTok Scraping**: Search and collect videos by keywords
- **Watermark-Free Downloads**: Download videos without watermarks using yt-dlp
- **Duplicate Prevention**: Smart duplicate detection and prevention
- **Facebook Auto-Posting**: Automatic posting with descriptions and hashtags
- **Web Dashboard**: Streamlit-based monitoring and control interface
- **Task Queue System**: Redis + RQ for reliable background processing
- **Scheduler**: Automated posting at configurable intervals
- **Logging & Monitoring**: Comprehensive logging and error handling
- **Free Tier Deployment**: Optimized for Render's free tier

## 📋 System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   TikTok API    │    │   yt-dlp        │    │   Facebook API  │
│                 │    │                 │    │                 │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Scraper       │    │   Downloader    │    │   Poster        │
│                 │    │                 │    │                 │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 ▼
                    ┌─────────────────┐
                    │   SQLite DB     │
                    │                 │
                    └─────────┬───────┘
                              │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   FastAPI       │ │   Redis Queue   │ │   Streamlit     │
│   API Server    │ │   (RQ)          │ │   Dashboard     │
│                 │ │                 │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## 🛠️ Tech Stack

- **Backend**: Python 3.11, FastAPI
- **Database**: SQLite
- **Task Queue**: Redis + RQ
- **Video Processing**: yt-dlp
- **TikTok Integration**: TikTokApi
- **Facebook Integration**: Facebook Graph API
- **Dashboard**: Streamlit
- **Deployment**: Render (Free Tier)

## 📁 Project Structure

```
tiktok-collector/
├── app/
│   ├── api.py              # FastAPI endpoints
│   ├── scraper.py          # TikTok video scraper
│   ├── downloader.py       # Video downloader
│   ├── poster.py           # Facebook poster
│   ├── scheduler.py        # Task scheduler
│   ├── worker.py           # RQ worker
│   ├── database.py         # SQLite database
│   └── logger.py           # Logging system
├── dashboard/
│   └── streamlit_app.py    # Streamlit dashboard
├── config/
│   └── config.json         # Configuration file
├── videos/                 # Downloaded videos
├── logs/                   # Log files
├── requirements.txt        # Python dependencies
├── render.yaml            # Render deployment
└── README.md              # This file
```

## 🚀 Quick Start (Native Python)

### Prerequisites

- Python 3.11+
- Redis server
- Facebook Page and Access Token
- TikTok API credentials (optional)

### Local Development

1. **Clone the repository**
```bash
git clone <repository-url>
cd tiktok-collector
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your credentials
```

4. **Start Redis**
```bash
redis-server
```

5. **Initialize database**
```bash
python -c "from app.database import Database; Database().init_database()"
```

6. **Start services**
```bash
# Start API server
uvicorn app.api:app --reload

# Start worker (in separate terminal)
python app/worker.py

# Start dashboard (in separate terminal)
streamlit run dashboard/streamlit_app.py
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Facebook Configuration
FACEBOOK_PAGE_ID=your_facebook_page_id
FACEBOOK_ACCESS_TOKEN=your_facebook_access_token

# Redis Configuration
REDIS_URL=redis://localhost:6379

# File Paths
DOWNLOAD_PATH=/videos
DATABASE_PATH=app/database.db
LOG_PATH=/logs

# System Configuration
MAX_POSTS_PER_DAY=15
SCRAPE_INTERVAL=30
POST_INTERVAL=60

# Limits
MAX_VIDEOS_PER_KEYWORD=50
MAX_DOWNLOAD_RETRIES=3
MAX_POST_RETRIES=3

# Optional: TikTok API
TIKTOK_MS_TOKEN=your_tiktok_ms_token
```

### Configuration File

Edit `config/config.json` for additional settings:

```json
{
  "FACEBOOK_PAGE_ID": "",
  "FACEBOOK_ACCESS_TOKEN": "",
  "REDIS_URL": "redis://localhost:6379",
  "DOWNLOAD_PATH": "/videos",
  "MAX_POSTS_PER_DAY": 15,
  "SCRAPE_INTERVAL": 30,
  "POST_INTERVAL": 60,
  "DATABASE_PATH": "app/database.db",
  "LOG_PATH": "/logs",
  "MAX_VIDEOS_PER_KEYWORD": 50,
  "MAX_DOWNLOAD_RETRIES": 3,
  "MAX_POST_RETRIES": 3
}
```

## 📊 Dashboard Features

The Streamlit dashboard provides:

- **System Overview**: Real-time statistics and health monitoring
- **Keywords Management**: Add/remove scraping keywords
- **Video Queue**: View and manage pending downloads/posts
- **Task Control**: Manual task execution and monitoring
- **Logs Viewer**: Real-time system logs
- **Settings**: Configure system parameters
- **Facebook Stats**: Page performance metrics

## 🔄 Workflow

1. **Keyword Setup**: Add keywords for video scraping
2. **Automatic Scraping**: System scrapes TikTok every 30 minutes
3. **Download Queue**: Videos queued for download
4. **Watermark Removal**: Videos downloaded without watermarks
5. **Post Queue**: Downloaded videos queued for Facebook posting
6. **Scheduled Posting**: Videos posted automatically (10-15 per day)
7. **Monitoring**: Dashboard tracks all activities

## 📱 Facebook Setup

1. **Create Facebook Page**: Create a Facebook page for posting
2. **Get Page ID**: Find your page ID in Facebook settings
3. **Create Access Token**:
   - Go to Facebook Developers
   - Create a new app with "Page Management" permissions
   - Generate a long-lived access token
4. **Configure Permissions**: Ensure video posting permissions

## 🐛 Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   - Ensure Redis server is running
   - Check REDIS_URL environment variable

2. **Facebook API Errors**
   - Verify access token is valid
   - Check page permissions
   - Ensure page ID is correct

3. **TikTok Scraping Issues**
   - Check TikTok API credentials
   - Verify keywords are valid
   - Monitor rate limiting

4. **Video Download Failures**
   - Check yt-dlp installation
   - Verify video URLs are accessible
   - Monitor storage space

### Debug Mode

Enable debug logging:

```bash
export DEBUG=true
```

This creates detailed debug logs in `/logs/debug.log`

## 🚀 Render Deployment (Native)

### Prerequisites

- GitHub repository with code
- Render account
- Facebook credentials configured

### Deployment Steps

1. **Connect GitHub**: Connect your repository to Render
2. **Create Services**:
   - Web Service (FastAPI) - Python build command
   - Worker Service (RQ tasks) - Python worker command
   - Redis Service (Managed)
3. **Configure Environment**: Set environment variables
4. **Deploy**: Push changes to trigger deployment

### Render Configuration

The `render.yaml` file contains the complete Render configuration:

- **Web Service**: FastAPI API server with Python runtime
- **Worker Service**: Background task processing
- **Redis Service**: Managed Redis instance
- **Environment Groups**: Secure credential management

**Build Commands:**
- Web Service: `pip install -r requirements.txt && uvicorn app.api:app --host 0.0.0.0 --port $PORT`
- Worker Service: `pip install -r requirements.txt && python app/worker.py`

## 📈 Monitoring

### System Health

- **API Health Check**: `/health` endpoint
- **Database Status**: Connection and query performance
- **Queue Status**: Task queue metrics
- **Resource Usage**: CPU, memory, disk space

### Logging

- **System Logs**: `/logs/system.log`
- **Error Logs**: `/logs/errors.log`
- **Debug Logs**: `/logs/debug.log` (debug mode only)
- **Database Logs**: Stored in SQLite logs table

## 🔧 API Endpoints

### Health & Stats
- `GET /health` - System health check
- `GET /stats` - System statistics
- `GET /logs` - Recent system logs

### Keywords
- `GET /keywords` - Get all keywords
- `POST /keywords` - Add keyword
- `DELETE /keywords/{keyword}` - Remove keyword

### Videos
- `GET /videos/pending-download` - Get pending downloads
- `GET /videos/pending-post` - Get pending posts

### Tasks
- `POST /tasks/scrape-all` - Scrape all keywords
- `POST /tasks/download-pending` - Download pending videos
- `POST /tasks/post-pending` - Post pending videos

## 🛡️ Security

- **Environment Variables**: Sensitive data in environment
- **Access Control**: API authentication (optional)
- **Rate Limiting**: Built-in rate limiting
- **Input Validation**: Request validation and sanitization
- **Error Handling**: Secure error responses

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:

1. Check the troubleshooting section
2. Review system logs
3. Create an issue on GitHub
4. Contact the development team

## 🔄 Updates

The system automatically:

- Updates TikTokApi for compatibility
- Refreshes Facebook tokens
- Cleans up old files and logs
- Monitors system health

## 📊 Performance

- **Scraping**: 20-50 videos per keyword
- **Downloading**: 1-2 videos per minute
- **Posting**: 1 video per minute (rate limited)
- **Storage**: ~10MB per video (varies)
- **Memory**: ~200MB base + video processing

## 🌐 Scaling

To scale beyond free tier limits:

1. **Upgrade Redis**: Larger Redis instance
2. **Add Workers**: Multiple worker processes
3. **Database**: Migrate to PostgreSQL
4. **Storage**: Use cloud storage for videos
5. **CDN**: Add CDN for video serving

---

**Built with ❤️ for automated content management**

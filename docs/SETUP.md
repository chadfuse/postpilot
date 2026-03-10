# Setup Guide (Native Python)

This guide will help you set up the TikTok Video Collector and Facebook Auto Publisher system using native Python deployment.

## 📋 Prerequisites

### Required Software
- Python 3.11 or higher
- Redis server
- Git

### Required Accounts & API Keys
- Facebook Page (with admin access)
- Facebook Developer Account
- Facebook App with Page Management permissions
- TikTok account (for MS token, optional)

## 🔧 Step-by-Step Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd tiktok-collector
```

### 2. Python Environment Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Redis Setup

#### 3.1 Install Redis

**On Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis
```

**On macOS with Homebrew:**
```bash
brew install redis
brew services start redis
```

**On Windows:**
Download Redis for Windows or use WSL

#### 3.2 Verify Redis Installation
```bash
redis-cli ping
# Should return: PONG
```

### 4. Facebook Setup

#### 4.1 Create Facebook Page
1. Go to Facebook and create a new page
2. Choose appropriate category (e.g., "Entertainment Website")
3. Add profile picture and cover photo
4. Note the Page ID (find in page URL or settings)

#### 4.2 Create Facebook App
1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Create a new app
3. Choose "Business" app type
4. Add "Page Management" product
5. Configure permissions:
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `pages_manage_engagement`

#### 4.3 Generate Access Token
1. In your Facebook App dashboard, go to "Page Management"
2. Use Graph API Explorer to generate token
3. Select your page and required permissions
4. Generate and copy the long-lived access token

#### 4.4 Test Facebook Integration
```bash
curl "https://graph.facebook.com/v18.0/me?access_token=YOUR_ACCESS_TOKEN"
```

### 5. Environment Configuration

#### 5.1 Create Environment File
```bash
cp .env.example .env
```

#### 5.2 Edit .env File
```env
# Facebook Configuration
FACEBOOK_PAGE_ID=your_facebook_page_id_here
FACEBOOK_ACCESS_TOKEN=your_long_lived_access_token_here

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

# Optional: TikTok MS Token (for better scraping)
TIKTOK_MS_TOKEN=your_tiktok_ms_token_here

# Debug Mode (set to true for detailed logging)
DEBUG=false
```

#### 5.3 Create Required Directories
```bash
mkdir -p videos logs
```

### 6. Database Initialization

```bash
# Initialize SQLite database
python -c "
from app.database import Database
db = Database()
db.init_database()
print('Database initialized successfully!')
"
```

### 7. Test the Setup

#### 7.1 Test Database Connection
```bash
python -c "
from app.database import Database
db = Database()
stats = db.get_system_stats()
print('Database test:', stats)
"
```

#### 7.2 Test Redis Connection
```bash
python -c "
import redis
r = redis.from_url('redis://localhost:6379')
r.ping()
print('Redis connection successful!')
"
```

#### 7.3 Test Facebook API
```bash
python -c "
from app.poster import FacebookPoster
from app.database import Database
import os

db = Database()
poster = FacebookPoster(
    db, 
    os.getenv('FACEBOOK_PAGE_ID'), 
    os.getenv('FACEBOOK_ACCESS_TOKEN')
)
stats = poster.get_page_stats()
print('Facebook API test:', stats)
"
```

### 8. Start the System

#### 8.1 Start API Server
```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

#### 8.2 Start Worker (New Terminal)
```bash
python app/worker.py
```

#### 8.3 Start Dashboard (New Terminal)
```bash
streamlit run dashboard/streamlit_app.py --server.port 8501
```

### 9. Verify Installation

1. **API Health Check**: Open http://localhost:8000/health
2. **Dashboard**: Open http://localhost:8501
3. **Add Keywords**: Use dashboard to add test keywords
4. **Test Scraping**: Run manual scraping task
5. **Monitor Logs**: Check logs in `/logs` directory

##  Render Deployment (Native Python)

### 1. Prepare for Render

1. Push code to GitHub repository
2. Ensure all secrets are configured as environment variables
3. Verify `render.yaml` configuration

### 2. Create Render Services

1. **Redis Service**: Create managed Redis instance
2. **Web Service**: Connect repository, set build command:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.api:app --host 0.0.0.0 --port $PORT`
3. **Worker Service**: Configure as background worker:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app/worker.py`

### 3. Configure Environment Variables

In Render dashboard, set:

```env
FACEBOOK_PAGE_ID=your_page_id
FACEBOOK_ACCESS_TOKEN=your_token
REDIS_URL=your_redis_url
MAX_POSTS_PER_DAY=15
SCRAPE_INTERVAL=30
POST_INTERVAL=60
```

### 4. Deploy

Push changes to GitHub to trigger automatic deployment.

## 🔍 Troubleshooting

### Common Issues

#### Redis Connection Failed
```bash
# Check if Redis is running
redis-cli ping

# Check Redis logs
tail -f /var/log/redis/redis-server.log

# Restart Redis
sudo systemctl restart redis
```

#### Facebook API Errors
1. Verify access token validity
2. Check page permissions
3. Ensure token has required scopes
4. Test token in Graph API Explorer

#### Database Issues
```bash
# Check database file
ls -la app/database.db

# Recreate database
rm app/database.db
python -c "from app.database import Database; Database().init_database()"
```

#### Permission Issues
```bash
# Fix directory permissions
chmod 755 videos logs
chmod 644 app/database.db
```

### Debug Mode

Enable detailed logging:

```bash
export DEBUG=true
# Or add to .env file
DEBUG=true
```

Check debug logs:
```bash
tail -f logs/debug.log
```

### Performance Issues

1. **Memory Usage**: Monitor with `htop` or `top`
2. **Disk Space**: Check with `df -h`
3. **Network**: Test internet connectivity
4. **Redis Memory**: Monitor with `redis-cli info memory`

## 📊 Monitoring Setup

### System Monitoring

```bash
# Monitor system resources
watch -n 5 'free -h && df -h && ps aux | grep python'

# Monitor Redis
redis-cli monitor

# Monitor logs
tail -f logs/system.log
```

### Health Checks

```bash
# API Health
curl http://localhost:8000/health

# Database Health
python -c "from app.database import Database; print(Database().get_system_stats())"

# Queue Health
python -c "import redis; r=redis.from_url('redis://localhost:6379'); print(r.info())"
```

## 🔄 Maintenance

### Daily Tasks
1. Check system logs
2. Monitor Facebook posting limits
3. Review video quality
4. Update keywords if needed

### Weekly Tasks
1. Clean up old video files
2. Update Facebook access token
3. Check system resource usage
4. Backup database

### Monthly Tasks
1. Update dependencies
2. Review and rotate secrets
3. Audit posted content
4. Performance optimization

## 📚 Next Steps

1. **Add Keywords**: Start with 5-10 relevant keywords
2. **Test Posting**: Manually post a few videos first
3. **Monitor Performance**: Watch system resources
4. **Scale Up**: Add more workers if needed
5. **Optimize**: Adjust intervals and limits

## 🆘 Getting Help

If you encounter issues:

1. Check the troubleshooting section
2. Review system logs in `/logs`
3. Test individual components
4. Create an issue on GitHub
5. Contact support team

---

**Happy automating! 🚀**

# PostPilot — System Guide

> **This file is the single source of truth for understanding the system.**
> Read this BEFORE making any changes.

---

## Purpose

PostPilot is an automated TikTok-to-Facebook video reposting pipeline.
It scrapes TikTok videos by keyword, downloads them, and posts them to a Facebook page.

---

## Pipeline (4 Stages)

```
SCRAPE → DOWNLOAD → POST → CLEANUP
```

### Stage 1: SCRAPE
- **File:** `app/scraper.py` → `TikTokScraper`
- **API:** tikwm.com search (`https://www.tikwm.com/api/feed/search`)
- **Input:** Keywords from `keywords` table
- **Output:** New rows in `videos` table with `downloaded=0, posted=0`
- **URL stored:** Permanent TikTok page URL (`https://www.tiktok.com/@author/video/{id}`)
  - CDN URLs expire in ~24h — NEVER store them
- **Dedup:** `tiktok_id` is UNIQUE — same video won't be added twice
- **Related keywords:** `scrape_related_for_keyword()` generates related search terms

### Stage 2: DOWNLOAD
- **File:** `app/downloader.py` → `VideoDownloader`
- **Picks:** Videos where `downloaded=0`
- **Process:**
  1. Resolve fresh CDN URL via tikwm API (using tiktok_id)
  2. Download .mp4 to `videos/` folder
  3. Update DB: `downloaded=1`, set `file_path`
- **Fallback chain:** tikwm refresh → tikwm page resolve → yt-dlp
- **Key rule:** ALWAYS resolve a fresh CDN URL at download time

### Stage 3: POST
- **File:** `app/poster.py` → `FacebookPoster`
- **Picks:** Videos where `downloaded=1 AND posted=0`
- **Process:**
  1. Generate description (caption + credit + hashtags)
  2. Upload .mp4 to Facebook page via Graph API v18.0
  3. Update DB: `posted=1`, store `facebook_post_id`
  4. **DELETE the local .mp4 file** to save disk space
- **Retry:** Up to 3 attempts with retry logic
- **Rate limit:** Controlled by MIN/MAX_POST_INTERVAL and MIN/MAX_POSTS_PER_DAY

### Stage 4: CLEANUP
- After posting, the .mp4 file is deleted (poster does this)
- DB record is KEPT forever — `facebook_post_id` prevents duplicate posts
- `tiktok_id` ensures the same video is never re-scraped or re-posted

---

## Critical Rules

### NEVER DO:
1. Delete DB records for posted videos (`posted=1`) — causes duplicate Facebook posts
2. Store expiring CDN URLs in the database — they expire in ~24h
3. Trust `downloaded=1` without checking if the file actually exists on disk
4. Run `st.secrets.get()` before `st.set_page_config()` in Streamlit
5. Use PUT method for config updates — the API uses POST
6. Set pending-post limit above 50 (API validation cap)

### ALWAYS DO:
1. Resolve fresh CDN URLs at download time via `_refresh_video_url()`
2. Check file exists on disk before attempting to post
3. Keep `st.set_page_config()` as the FIRST Streamlit command
4. Preserve posted video records during any cleanup operation
5. Invalidate caches (`video_cache.clear()`, `stats_cache.clear()`) after mutations

---

## Database Schema

### `videos` table (core)
| Column | Type | Purpose |
|--------|------|---------|
| `tiktok_id` | TEXT UNIQUE | Dedup key — never changes |
| `video_url` | TEXT | Permanent TikTok page URL |
| `caption` | TEXT | Video caption from TikTok |
| `author` | TEXT | Creator username |
| `hashtags` | TEXT | JSON array of hashtags |
| `file_path` | TEXT | Local path to .mp4 (null if not downloaded) |
| `downloaded` | BOOLEAN | 0=pending, 1=downloaded |
| `posted` | BOOLEAN | 0=not posted, 1=posted to Facebook |
| `facebook_post_id` | TEXT | Facebook post ID (set after posting) |

### `keywords` table
| Column | Type | Purpose |
|--------|------|---------|
| `keyword` | TEXT UNIQUE | Search term for TikTok |
| `active` | BOOLEAN | Whether to include in scraping |

### `logs` table
| Column | Type | Purpose |
|--------|------|---------|
| `type` | TEXT | e.g. `info:scheduler`, `error:poster` |
| `message` | TEXT | Log message |
| `details` | TEXT | Extra context |

---

## Architecture

```
DASHBOARD (Streamlit :8501)
    │
    ▼ HTTP requests
API SERVER (FastAPI :8000)  ← api_optimized.py
    │
    ├── scraper.py      (tikwm.com API)
    ├── downloader.py   (tikwm + yt-dlp)
    ├── poster.py       (Facebook Graph API)
    ├── scheduler.py    (APScheduler — background automation)
    └── database.py     (SQLite)
    
Storage:
    ├── app/database.db       (SQLite database)
    ├── videos/*.mp4          (temporary — deleted after posting)
    └── config/config.json    (settings + Facebook credentials)
```

---

## API Endpoints (api_optimized.py)

### Health & Status
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Server health check |
| GET | `/stats` | System statistics (cached) |
| GET | `/tasks/status` | Queue counts from DB |
| GET | `/scheduler/next-post` | Next post timing info |

### Videos
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/videos` | List all videos |
| GET | `/videos/pending-download` | Videos needing download |
| GET | `/videos/pending-post` | Downloaded videos ready to post |
| DELETE | `/videos/pending-download` | Clear pending downloads (preserves posted) |
| DELETE | `/videos/pending-post` | Clear pending posts |

### Keywords
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/keywords` | List all keywords |
| POST | `/keywords` | Add a keyword |
| DELETE | `/keywords/{keyword}` | Remove a keyword |

### Tasks (Direct Execution)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/tasks/scrape-keyword/{keyword}` | Scrape single keyword |
| POST | `/tasks/scrape-all` | Scrape all keywords + related |
| POST | `/tasks/scrape-unlimited` | Smart tiered scraping + related |
| POST | `/tasks/download-pending` | Download pending videos |
| POST | `/tasks/download/{tiktok_id}` | Download single video |
| POST | `/tasks/post-pending` | Post pending videos to Facebook |
| POST | `/tasks/post/{tiktok_id}` | Post single video to Facebook |

### Config & Facebook
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/config` | Get system configuration |
| POST | `/config` | Update system configuration |
| GET | `/facebook/settings` | Facebook connection info |
| GET | `/facebook/stats` | Facebook page statistics |

### Admin
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/admin/cleanup-missing-videos` | Sync DB with actual files on disk |

---

## Scheduler Jobs (scheduler.py)

| Job | Interval | Action |
|-----|----------|--------|
| Scrape all keywords | Every 30 min | Scrapes TikTok for new videos |
| Download pending | Every 15 min | Downloads up to 10 videos |
| Post to Facebook | Every 5 min | Posts 1 video (within daily limits) |
| Daily cleanup | 2:00 AM | Housekeeping |
| Update stats | Every 1 hour | Logs system statistics |
| Sync Facebook stats | Every 6 hours | Checks Facebook page stats |

### Posting Rate Logic
1. Check `posts_today < MAX_POSTS_PER_DAY` (default 11)
2. If `posts_today >= MIN_POSTS_PER_DAY` (default 5), 50% random chance to skip
3. Check `time_since_last_post >= MIN_POST_INTERVAL` (default 5 min)
4. Pick 1 pending video, post it, update DB

---

## Configuration (config/config.json)

```json
{
  "FACEBOOK_PAGE_ID": "...",
  "FACEBOOK_ACCESS_TOKEN": "...",
  "MIN_POSTS_PER_DAY": 5,
  "MAX_POSTS_PER_DAY": 11,
  "MIN_POST_INTERVAL": 5,
  "MAX_POST_INTERVAL": 20,
  "MIN_SCRAPE_INTERVAL": 20,
  "MAX_SCRAPE_INTERVAL": 60
}
```

---

## Smart Unlimited Scraping

Tiered approach for maximizing content:

| Tier | Keywords | Videos/Keyword | Related Terms |
|------|----------|---------------|---------------|
| 1 | Top 3 | 200 | 3 related terms each |
| 2 | Next 7 | 150 | 2 related terms each |
| 3 | Next 15 | 100 | 1 related term each |
| 4 | Remaining | 75 | None |

Related keywords are generated by `scrape_related_for_keyword()` and combine the base keyword with contextual terms (e.g., "slingshot" + "shooting", "aim", "target").

---

## Dashboard Pages (streamlit_app.py)

| Tab | Purpose |
|-----|---------|
| **Videos** | View pending downloads, pending posts, manage video pipeline |
| **Keywords** | Add/remove keywords, bulk import |
| **Tasks** | Manual scrape/download/post buttons, queue status |
| **Settings** | Adjust posting intervals, scrape intervals, daily limits |
| **Facebook** | Facebook connection status, page info |

---

## Known Issues & Gotchas

1. **Ghost downloads:** Scheduler's `_download_pending_videos` previously simulated downloads (marked downloaded=1 without actually downloading). This creates entries where `downloaded=1` but no file exists. Fix: run `/admin/cleanup-missing-videos`.

2. **Path inconsistency:** Some `file_path` entries use `videos/xxx.mp4` (relative), others `/videos/xxx.mp4` (absolute from root). New downloads use `videos/xxx.mp4` (relative, correct).

3. **CDN URL expiration:** TikTok CDN URLs expire in ~24h. The downloader always resolves fresh URLs at download time. The scraper stores permanent TikTok page URLs.

4. **File deletion after posting:** The poster deletes .mp4 files after successful Facebook upload. This is by design to save disk space. The DB record remains for dedup.

5. **Rate limiting:** API endpoints have rate limits via `@rate_limit()` decorator. Dashboard has client-side caching via `api_cache.py`.

---

## File Map

```
windsurf-project/
├── app/
│   ├── api_optimized.py     ← Main API server (FastAPI)
│   ├── api.py               ← Original API (not used in production)
│   ├── database.py          ← SQLite database class
│   ├── database.db          ← SQLite database file
│   ├── scraper.py           ← TikTok scraper (tikwm API)
│   ├── downloader.py        ← Video downloader
│   ├── poster.py            ← Facebook poster (Graph API)
│   ├── scheduler.py         ← APScheduler background jobs
│   ├── memory_cache.py      ← In-memory caching
│   └── rate_limiter.py      ← Rate limiting decorators
├── dashboard/
│   ├── streamlit_app.py     ← Main dashboard UI
│   ├── api_cache.py         ← Dashboard-side API caching
│   ├── keywords_bulk.py     ← Bulk keyword import
│   ├── keywords_csv.py      ← CSV keyword import
│   └── advanced_api_client.py ← Advanced async API client (optional)
├── config/
│   └── config.json          ← System configuration + Facebook creds
├── videos/                  ← Temporary video storage (deleted after posting)
├── start_optimized.sh       ← Startup script
└── SYSTEM_GUIDE.md          ← THIS FILE
```

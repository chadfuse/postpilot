import os
import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Configuration — env var takes priority (Render), then secrets.toml, then local default
API_BASE_URL = os.getenv("API_BASE_URL") or st.secrets.get("API_BASE_URL", "http://localhost:8000")

# Page configuration
st.set_page_config(
    page_title="PostPilot - TikTok to Facebook Automation",
    page_icon="PP",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Clean Light Theme
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">', unsafe_allow_html=True)

st.markdown("""<style>
.stApp { background-color: #ffffff !important; }
[data-testid="stSidebar"] { background-color: #f8f9fa !important; border-right: 1px solid #e9ecef; }
.status-running { color: #28a745 !important; font-weight: bold; }
.status-error   { color: #dc3545 !important; font-weight: bold; }
.status-warning { color: #ffc107 !important; font-weight: bold; }

/* Sidebar nav buttons */
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    text-align: left;
    background: transparent;
    color: #495057;
    border: none;
    border-radius: 8px;
    padding: 0.6rem 1rem;
    font-size: 0.95rem;
    font-weight: 500;
    box-shadow: none;
    transition: background 0.15s;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #e9ecef;
    color: #212529;
    transform: none;
    box-shadow: none;
}
[data-testid="stSidebar"] .stButton > button:focus {
    box-shadow: none;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #667eea !important;
    color: #fff !important;
    font-weight: 600;
    box-shadow: none;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: #5a6fd6 !important;
    transform: none;
    box-shadow: none;
}
</style>""", unsafe_allow_html=True)

# Helper functions
def get_time_until_post(scheduled_time: str) -> str:
    """Calculate time until scheduled post"""
    if not scheduled_time:
        return "Will be posted in queue order"
    
    try:
        from datetime import datetime
        scheduled_dt = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
        now = datetime.now()
        
        if scheduled_dt <= now:
            return "Posting now..."
        
        delta = scheduled_dt - now
        total_minutes = int(delta.total_seconds() / 60)
        
        if total_minutes < 60:
            return f"Will be posted in {total_minutes} minute{'s' if total_minutes != 1 else ''}"
        elif total_minutes < 1440:  # Less than 24 hours
            hours = total_minutes // 60
            minutes = total_minutes % 60
            if minutes == 0:
                return f"Will be posted in {hours} hour{'s' if hours != 1 else ''}"
            else:
                return f"Will be posted in {hours}h {minutes}m"
        else:
            days = total_minutes // 1440
            hours = (total_minutes % 1440) // 60
            if hours == 0:
                return f"Will be posted in {days} day{'s' if days != 1 else ''}"
            else:
                return f"Will be posted in {days}d {hours}h"
    except:
        return "Will be posted in queue order"

def api_request(endpoint: str, method: str = "GET", data: dict = None):
    """Make API request"""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        elif method == "PUT":
            response = requests.put(url, json=data, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, timeout=10)
        else:
            return None
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API Error: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        st.error(f"Connection Error: {str(e)}")
        return None

def format_number(num: int) -> str:
    """Format large numbers"""
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    else:
        return str(num)

def get_status_color(status: str) -> str:
    """Get status color"""
    if status in ["running", "connected", "healthy"]:
        return "status-running"
    elif status in ["error", "failed", "disconnected"]:
        return "status-error"
    else:
        return "status-warning"

# Sidebar branding
st.sidebar.markdown("""
<div style="text-align:center; padding: 0.5rem 0 1rem 0;">
    <div style="font-size: 1.6rem; font-weight: 700; color: #212529;">PostPilot</div>
    <div style="font-size: 0.8rem; color: #6c757d;">TikTok → Facebook Automation</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")

# Vertical tab navigation with Font Awesome icons
NAV_ITEMS = [
    ("Dashboard",  "fa-solid fa-gauge-high"),
    ("Keywords",   "fa-solid fa-hashtag"),
    ("Videos",     "fa-solid fa-film"),
    ("Tasks",      "fa-solid fa-list-check"),
    ("Logs",       "fa-solid fa-scroll"),
    ("Settings",   "fa-solid fa-gear"),
    ("Facebook",   "fa-brands fa-facebook"),
]

if "page" not in st.session_state:
    st.session_state.page = "Dashboard"

for name, icon in NAV_ITEMS:
    is_active = st.session_state.page == name
    btn_type = "primary" if is_active else "secondary"
    if st.sidebar.button(f"  {name}", key=f"nav_{name}", type=btn_type, use_container_width=True):
        st.session_state.page = name
        st.rerun()

page = st.session_state.page

# System Health in sidebar
st.sidebar.markdown("---")
health = api_request("/health")
if health:
    status = health.get('status', 'unknown')
    if status == 'healthy':
        st.sidebar.success(f"System: {status.upper()}")
    else:
        st.sidebar.error(f"System: {status.upper()}")
    col_h1, col_h2 = st.sidebar.columns(2)
    col_h1.caption(f"DB: {health.get('database', '?')}")
    col_h2.caption(f"Redis: {health.get('redis', '?')}")

# Main content
if page == "Dashboard":
    st.title("System Dashboard")
    st.caption("Real-time monitoring of your TikTok → Facebook automation")
    
    # Get system stats
    stats = api_request("/stats")
    if stats and stats.get("success"):
        db_stats = stats.get("database", {})
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Videos", format_number(db_stats.get('overall', {}).get('total_videos', 0)))
        with col2:
            st.metric("Downloaded Today", format_number(db_stats.get('today', {}).get('downloaded', 0)))
        with col3:
            st.metric("Posted Today", format_number(db_stats.get('today', {}).get('posted', 0)))
        with col4:
            st.metric("Active Keywords", format_number(db_stats.get('overall', {}).get('keywords', 0)))
        
        st.markdown("---")
        
        # Charts
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Today's Activity")
            today_data = db_stats.get('today', {})
            
            fig = go.Figure(data=[
                go.Bar(name='Scraped', x=['Scraped', 'Downloaded', 'Posted'], 
                      y=[today_data.get('scraped', 0), today_data.get('downloaded', 0), today_data.get('posted', 0)],
                      marker_color=['#1f77b4', '#ff7f0e', '#2ca02c'])
            ])
            fig.update_layout(title="Today's Video Processing", yaxis_title="Count")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("Overall Progress")
            overall_data = db_stats.get('overall', {})
            
            fig = go.Figure(data=[
                go.Pie(labels=['Downloaded', 'Not Downloaded', 'Posted'],
                       values=[overall_data.get('downloaded', 0), 
                              overall_data.get('total_videos', 0) - overall_data.get('downloaded', 0),
                              overall_data.get('posted', 0)],
                       hole=0.3)
            ])
            fig.update_layout(title="Video Processing Status")
            st.plotly_chart(fig, use_container_width=True)
        
        # Queue status
        if stats.get("queue"):
            st.subheader("Task Queue Status")
            queue_data = stats.get("queue", {})
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Pending", queue_data.get("pending_jobs", 0))
            with col2:
                st.metric("Failed", queue_data.get("failed_jobs", 0))
            with col3:
                st.metric("Scheduled", queue_data.get("scheduled_jobs", 0))
            with col4:
                st.metric("Started", queue_data.get("started_jobs", 0))

elif page == "Keywords":
    st.title("Keywords Management")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Current Keywords")
        
        keywords_data = api_request("/keywords")
        if keywords_data and keywords_data.get("success"):
            keywords = keywords_data.get("keywords", [])
            
            if keywords:
                df = pd.DataFrame(keywords, columns=["Keyword"])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No keywords configured yet")
    
    with col2:
        st.subheader("Add Keyword")
        
        new_keyword = st.text_input("Enter keyword:")
        if st.button("Add Keyword", type="primary"):
            if new_keyword.strip():
                result = api_request("/keywords", "POST", {"keyword": new_keyword.strip()})
                if result and result.get("success"):
                    st.success(result.get("message", "Keyword added successfully"))
                    st.rerun()
                else:
                    st.error("Failed to add keyword")
            else:
                st.error("Please enter a keyword")
        
        st.markdown("---")
        
        st.subheader("Remove Keyword")
        
        keywords_data = api_request("/keywords")
        if keywords_data and keywords_data.get("success"):
            keywords = keywords_data.get("keywords", [])
            
            if keywords:
                keyword_to_remove = st.selectbox("Select keyword to remove:", keywords)
                if st.button("Remove Keyword", type="secondary"):
                    result = api_request(f"/keywords/{keyword_to_remove}", "DELETE")
                    if result and result.get("success"):
                        st.success(result.get("message", "Keyword removed successfully"))
                        st.rerun()
                    else:
                        st.error("Failed to remove keyword")

elif page == "Videos":
    st.title("Videos Management")
    st.caption("Manage your video pipeline from download to posting")
    
    # Next posting indicator
    posting_info = api_request("/scheduler/next-post")
    if posting_info and posting_info.get("success"):
        next_post_time = posting_info.get("next_post_time")
        queue_count = posting_info.get("queue_count", 0)
        
        if next_post_time:
            st.info(f"Next scheduled post: {next_post_time} ({queue_count} videos in queue)")
        else:
            st.info("No posts scheduled - videos will post in queue order")
    
    # Add refresh button for live updates
    col_refresh, col_space = st.columns([1, 5])
    with col_refresh:
        if st.button("Refresh", key="refresh_videos"):
            st.rerun()
    
    # Get queue status once for the whole page
    queue_data = api_request("/tasks/status")
    dl_queue = queue_data.get("queues", {}).get("downloader", {}) if queue_data else {}
    dl_pending = dl_queue.get("pending", 0) if dl_queue else 0

    # Tabs for different video views
    tab1, tab2, tab3, tab4 = st.tabs(["Pending Downloads", "Pending Posts", "All Videos", "Task Status"])
    
    with tab1:
        st.subheader("Videos Pending Download")
        
        pending_downloads = api_request("/videos/pending-download?limit=500")
        if pending_downloads and pending_downloads.get("success"):
            videos = pending_downloads.get("videos", [])
            
            if videos:
                avg_download_sec = 45  # estimated per video
                
                # Initialize session state for checkboxes
                if 'selected_downloads' not in st.session_state:
                    st.session_state.selected_downloads = {}
                
                st.subheader("Select videos to download:")
                for i, video in enumerate(videos):
                    tid = video.get('tiktok_id', 'Unknown')
                    author = video.get('author', '?')
                    position = i + 1
                    eta_sec = (position + dl_pending) * avg_download_sec
                    eta_min = eta_sec // 60
                    eta_sec_rem = eta_sec % 60
                    eta_str = f"{eta_min}m {eta_sec_rem}s" if eta_min > 0 else f"{eta_sec}s"
                    
                    # Checkbox for selection
                    checked = st.checkbox(f"#{position} • ~{eta_str} | @{author} — {tid}", 
                                       key=f"dl_check_{tid}",
                                       value=st.session_state.selected_downloads.get(tid, False))
                    st.session_state.selected_downloads[tid] = checked
                    
                    if checked:
                        with st.expander(f"Details for {tid}", expanded=False):
                            col1, col2 = st.columns([3, 1])
                            
                            with col1:
                                st.write(f"**TikTok ID:** {tid}")
                                st.write(f"**Author:** @{author}")
                                st.write(f"**Caption:** {(video.get('caption') or 'No caption')[:100]}...")
                                st.write(f"**Hashtags:** {', '.join(video.get('hashtags', []))}")
                                st.caption(f"Position {position} of {len(videos)} pending • {dl_pending} jobs in queue")
                            
                            with col2:
                                if st.button("Download Now", key=f"download_{tid}", use_container_width=True):
                                    result = api_request(f"/tasks/download/{tid}", "POST")
                                    if result and result.get("success"):
                                        st.success("Queued")
                                        st.rerun()
                                    else:
                                        st.error("Failed")
            else:
                st.info("No videos pending download")
        
        # Bulk operations
        selected_count = sum(1 for v in videos if st.session_state.selected_downloads.get(v.get('tiktok_id'), False)) if videos else 0
        
        col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 1])
        with col_btn1:
            if st.button(f"Download All Pending", type="primary"):
                result = api_request("/tasks/download-pending", "POST")
                if result and result.get("success"):
                    st.success(result.get("message", "Download task queued"))
        with col_btn2:
            if st.button(f"Download Selected ({selected_count})", type="primary", disabled=selected_count == 0):
                selected_ids = [v.get('tiktok_id') for v in videos if st.session_state.selected_downloads.get(v.get('tiktok_id'), False)]
                success_count = 0
                for tid in selected_ids:
                    result = api_request(f"/tasks/download/{tid}", "POST")
                    if result and result.get("success"):
                        success_count += 1
                if success_count > 0:
                    st.success(f"Queued {success_count}/{len(selected_ids)} videos for download")
                    st.session_state.selected_downloads = {}  # Clear selections
                    st.rerun()
        with col_btn3:
            if st.button("Clear All Pending", key="clear_dl", type="secondary"):
                if st.session_state.get("confirm_clear_dl"):
                    result = api_request("/videos/pending-download", "DELETE")
                    if result and result.get("success"):
                        st.success(result.get("message", "Cleared pending downloads"))
                        st.session_state["confirm_clear_dl"] = False
                        st.rerun()
                else:
                    st.session_state["confirm_clear_dl"] = True
                    st.warning("Click again to confirm clearing all pending downloads")
        
        # Download progress indicator
        if dl_pending > 0:
            st.info(f"{dl_pending} videos currently downloading...")
            # Show a simple progress bar while downloads are in queue
            progress_bar = st.progress(0.5, text=f"Processing {dl_pending} downloads...")
            # The bar will auto-refresh when page reloads after downloads complete
    
    with tab2:
        st.subheader("Videos Pending Posting")
        
        pending_posts = api_request("/videos/pending-post?limit=500")
        if pending_posts and pending_posts.get("success"):
            videos = pending_posts.get("videos", [])
            
            if videos:
                # Initialize session state for checkboxes
                if 'selected_posts' not in st.session_state:
                    st.session_state.selected_posts = {}
                
                st.subheader("Select videos to post:")
                for i, video in enumerate(videos):
                    tid = video.get('tiktok_id', 'Unknown')
                    author = video.get('author', 'Unknown')
                    
                    # Calculate posting time
                    scheduled_time = video.get('scheduled_time')
                    time_info = get_time_until_post(scheduled_time)
                    
                    # Checkbox for selection with time info
                    checkbox_label = f"#{i+1} | @{author} — {tid}"
                    checked = st.checkbox(checkbox_label, 
                                       key=f"post_check_{tid}",
                                       value=st.session_state.selected_posts.get(tid, False))
                    st.session_state.selected_posts[tid] = checked
                    
                    # Show posting time info
                    st.caption(f"Scheduled: {time_info}")
                    
                    if checked:
                        with st.expander(f"Details for {tid}", expanded=False):
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                st.write(f"**TikTok ID:** {tid}")
                                st.write(f"**Author:** @{author}")
                                st.write(f"**Caption:** {(video.get('caption') or 'No caption')[:120]}...")
                                st.write(f"**Hashtags:** {', '.join(video.get('hashtags', []))}")
                                if video.get('file_path'):
                                    st.write(f"**File:** {video['file_path']}")
                            
                            with col2:
                                if st.button("Post Now", key=f"post_now_{tid}", type="primary", use_container_width=True):
                                    result = api_request(f"/tasks/post/{tid}", "POST")
                                    if result and result.get("success"):
                                        st.success("Posted")
                                        st.rerun()
                                    else:
                                        st.error("Failed to queue")
                                
                                st.caption("— or schedule —")
                                sched_date = st.date_input("Date", key=f"sched_date_{tid}", label_visibility="collapsed")
                                sched_time = st.time_input("Time", key=f"sched_time_{tid}", label_visibility="collapsed", step=300)
                                if st.button("Schedule", key=f"sched_btn_{tid}", use_container_width=True):
                                    scheduled_dt = datetime.combine(sched_date, sched_time).isoformat()
                                    result = api_request(f"/tasks/post/{tid}/schedule?scheduled_at={scheduled_dt}", "POST")
                                    if result and result.get("success"):
                                        st.success(f"Scheduled for {sched_date} {sched_time}")
                                    else:
                                        st.error("Failed to schedule")
            else:
                st.info("No videos pending posting")
        
        # Bulk operations
        selected_post_count = sum(1 for v in videos if st.session_state.selected_posts.get(v.get('tiktok_id'), False)) if videos else 0
        
        col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 1])
        with col_btn1:
            if st.button("Post All Pending", type="primary"):
                result = api_request("/tasks/post-pending", "POST")
                if result and result.get("success"):
                    st.success(result.get("message", "Posting task queued"))
        with col_btn2:
            if st.button(f"Post Selected ({selected_post_count})", type="primary", disabled=selected_post_count == 0):
                selected_ids = [v.get('tiktok_id') for v in videos if st.session_state.selected_posts.get(v.get('tiktok_id'), False)]
                success_count = 0
                for tid in selected_ids:
                    result = api_request(f"/tasks/post/{tid}", "POST")
                    if result and result.get("success"):
                        success_count += 1
                if success_count > 0:
                    st.success(f"Queued {success_count}/{len(selected_ids)} videos for posting")
                    st.session_state.selected_posts = {}  # Clear selections
                    st.rerun()
        with col_btn3:
            if st.button("Clear All Pending", key="clear_post", type="secondary"):
                if st.session_state.get("confirm_clear_post"):
                    result = api_request("/videos/pending-post", "DELETE")
                    if result and result.get("success"):
                        st.success(result.get("message", "Cleared pending posts"))
                        st.session_state["confirm_clear_post"] = False
                        st.rerun()
                else:
                    st.session_state["confirm_clear_post"] = True
                    st.warning("Click again to confirm clearing all pending posts")
    
    with tab3:
        st.subheader("All Videos")

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filter_dl = st.selectbox("Downloaded", ["All", "Yes", "No"], key="filter_dl")
        with col_f2:
            filter_posted = st.selectbox("Posted", ["All", "Yes", "No"], key="filter_posted")

        params = "/videos?limit=100"
        if filter_dl != "All":
            params += f"&downloaded={'true' if filter_dl == 'Yes' else 'false'}"
        if filter_posted != "All":
            params += f"&posted={'true' if filter_posted == 'Yes' else 'false'}"

        all_videos_data = api_request(params)
        if all_videos_data and all_videos_data.get("success"):
            videos = all_videos_data.get("videos", [])
            st.caption(f"{len(videos)} video(s) found")
            if videos:
                def _status(v):
                    if v.get("posted"):     return "Posted"
                    if v.get("downloaded"): return "Downloaded"
                    return "Pending Download"
                rows = []
                for v in videos:
                    rows.append({
                        "Status": _status(v),
                        "TikTok ID": v.get("tiktok_id", ""),
                        "Author": v.get("author", ""),
                        "Caption": (v.get("caption") or "")[:60],
                        "Created": v.get("created_at", "")[:16],
                    })
                import pandas as pd
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
                
                # Individual delete buttons
                st.subheader("Delete Individual Videos")
                selected_id = st.selectbox("Select video to delete:", [""] + [v["tiktok_id"] for v in videos], key="delete_select")
                if selected_id:
                    if st.button("Delete Selected Video", type="secondary"):
                        result = api_request(f"/videos/{selected_id}", "DELETE")
                        if result and result.get("success"):
                            st.success(result.get("message", "Video deleted"))
                            st.rerun()
                        else:
                            st.error("Failed to delete video")
            else:
                st.info("No videos match the selected filters")
    
    with tab4:
        st.subheader("Task Queue Status")
        status = api_request("/tasks/status")
        if status and status.get("success"):
            for qname, qinfo in status.get("queues", {}).items():
                with st.expander(f"{qname.title()} Queue"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Pending", qinfo.get("pending", 0))
                    with col2:
                        st.metric("Failed", qinfo.get("failed", 0))
                    with col3:
                        st.metric("Jobs Shown", len(qinfo.get("jobs", [])))
                    
                    jobs = qinfo.get("jobs", [])
                    if jobs:
                        for job in jobs:
                            with st.container():
                                cols = st.columns([2, 2, 2, 2])
                                cols[0].write(f"**ID:** `{job['id']}`")
                                cols[1].write(f"**Func:** {job['func'].replace('_', ' ').title()}")
                                cols[2].write(f"**Status:** {job['status'].title()}")
                                if job.get('created_at'):
                                    created = datetime.fromisoformat(job['created_at'])
                                    cols[3].write(f"**Age:** {(datetime.now() - created).total_seconds():.0f}s")
                    else:
                        st.info("No jobs in queue")
        else:
            st.error("Failed to load task status")

elif page == "Tasks":
    st.title("Task Management")
    
    # Next posting indicator in Tasks too
    posting_info = api_request("/scheduler/next-post")
    if posting_info and posting_info.get("success"):
        next_post_time = posting_info.get("next_post_time")
        queue_count = posting_info.get("queue_count", 0)
        interval_range = posting_info.get("interval_range", "")
        
        if next_post_time:
            st.info(f"Next scheduled post: {next_post_time} ({queue_count} videos in queue)")
        else:
            st.info(f"Next post in {interval_range} ({queue_count} videos in queue order)")

    # --- Live stats banner ---
    stats      = api_request("/stats")
    dl_data    = api_request("/videos/pending-download?limit=200")
    post_data  = api_request("/videos/pending-post?limit=200")

    db_overall    = stats.get("database", {}).get("overall", {}) if stats else {}
    pending_dl    = len(dl_data.get("videos", []))   if dl_data   else 0
    pending_post  = len(post_data.get("videos", [])) if post_data else 0
    posted_today  = stats.get("database", {}).get("today", {}).get("posted", 0) if stats else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Scraped",    db_overall.get("total_videos", 0))
    c2.metric("Pending Download", pending_dl)
    c3.metric("Pending Post",     pending_post)
    c4.metric("Posted Today",     posted_today)

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Manual Tasks")

        if st.button("Scrape All Keywords", type="primary", use_container_width=True):
            result = api_request("/tasks/scrape-all", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Scraping task queued"))
            else:
                st.error("Failed to queue scraping task")

        if st.button("Smart Unlimited Scraping", type="primary", use_container_width=True):
            st.info("This will deeply scrape your keywords + find related content")
            result = api_request("/tasks/scrape-unlimited", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Smart scraping task queued"))
            else:
                st.error("Failed to queue smart scraping task")

        if st.button("Download Pending Videos", use_container_width=True):
            result = api_request("/tasks/download-pending", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Download task queued"))
            else:
                st.error("Failed to queue download task")

        if st.button("Post Pending Videos", use_container_width=True):
            result = api_request("/tasks/post-pending", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Posting task queued"))
            else:
                st.error("Failed to queue posting task")

        if st.button("Cleanup Old Files", use_container_width=True):
            result = api_request("/tasks/cleanup", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Cleanup task queued"))
            else:
                st.error("Failed to queue cleanup task")

    with col2:
        st.subheader("Queue Status")

        task_status = api_request("/tasks/status")
        if task_status and task_status.get("success"):
            queues = task_status.get("queues", {})
            total_pending = sum(q.get("pending", 0) for q in queues.values())
            total_failed  = sum(q.get("failed", 0) for q in queues.values())

            mc1, mc2 = st.columns(2)
            mc1.metric("Jobs in Queue", total_pending)
            mc2.metric("Failed Jobs", total_failed)

            for qname, qinfo in queues.items():
                icon = {"scraper": "S", "downloader": "D", "poster": "P", "cleanup": "C"}.get(qname, "-")
                p = qinfo.get("pending", 0)
                f = qinfo.get("failed", 0)
                status_str = f"pending: {p}  |  failed: {f}"
                st.write(f"{icon} **{qname.title()}** — {status_str}")

                for job in qinfo.get("jobs", []):
                    age = ""
                    if job.get("created_at"):
                        secs = (datetime.now() - datetime.fromisoformat(job["created_at"])).total_seconds()
                        age = f"  ({int(secs)}s ago)"
                    st.caption(f"  `{job['id']}` · {job['func'].split('.')[-1]} · {job['status']}{age}")
        else:
            st.warning("Queue status unavailable — Redis may be disconnected")

elif page == "Logs":
    st.title("System Logs")
    
    # Log filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        log_limit = st.selectbox("Show last", [50, 100, 200, 500], index=1)
    
    with col2:
        log_type = st.selectbox("Log type", ["All", "info", "error", "warning"])
    
    with col3:
        if st.button("Refresh"):
            st.rerun()
    
    # Get logs
    logs = api_request(f"/logs?limit={log_limit}")
    if logs and logs.get("success"):
        log_entries = logs.get("logs", [])
        
        if log_entries:
            # Filter logs by type if specified
            if log_type != "All":
                log_entries = [log for log in log_entries if log_type in log.get("type", "").lower()]
            
            for log in log_entries:
                log_type_display = log.get("type", "unknown").split(":")[0].upper()
                component = log.get("type", "unknown").split(":")[1] if ":" in log.get("type", "") else "unknown"
                
                # Color coding
                if "error" in log.get("type", "").lower():
                    st.markdown(f"**{log_type_display}** - **{component}**")
                elif "warning" in log.get("type", "").lower():
                    st.markdown(f"**{log_type_display}** - **{component}**")
                else:
                    st.markdown(f"**{log_type_display}** - **{component}**")
                
                st.write(f"**Message:** {log.get('message', 'No message')}")
                if log.get("details"):
                    st.write(f"**Details:** {log.get('details')}")
                st.write(f"**Time:** {log.get('created_at', 'Unknown')}")
                st.markdown("---")
        else:
            st.info("No logs found")
    else:
        st.error("Failed to fetch logs")

elif page == "Settings":
    st.title("System Settings")
    st.caption("Configure automation parameters and intervals")
    
    # Get current config
    config_data = api_request("/config")
    if config_data and config_data.get("success"):
        current_config = config_data.get("config", {})
        
        st.subheader("System Configuration")
        st.caption("Set ranges for randomized automation behavior")
        
        col1, col2 = st.columns(2)
        
        posts_range = st.slider(
            "Posts Per Day (min – max)",
            min_value=1, max_value=50,
            value=(
                int(current_config.get("MIN_POSTS_PER_DAY", 10)),
                int(current_config.get("MAX_POSTS_PER_DAY", 15))
            ),
            step=1,
            help="The scheduler will post a random number of videos within this range each day"
        )
        st.caption(f"Will post between **{posts_range[0]}** and **{posts_range[1]}** videos per day")

        col1, col2 = st.columns(2)
        with col1:
            scrape_range = st.slider(
                "Scrape Interval (min – max minutes)",
                min_value=5, max_value=480,
                value=(
                    int(current_config.get("MIN_SCRAPE_INTERVAL", 20)),
                    int(current_config.get("MAX_SCRAPE_INTERVAL", 60))
                ),
                step=5,
                help="Scraper will run at a random interval within this range"
            )
            st.caption(f"Scrapes every **{scrape_range[0]}–{scrape_range[1]} min**")
        with col2:
            post_range = st.slider(
                "Post Interval (min – max minutes)",
                min_value=5, max_value=480,
                value=(
                    int(current_config.get("MIN_POST_INTERVAL", 30)),
                    int(current_config.get("MAX_POST_INTERVAL", 90))
                ),
                step=5,
                help="Gap between posts will be a random value within this range"
            )
            st.caption(f"Posts every **{post_range[0]}–{post_range[1]} min**")

        if st.button("💾 Save Settings", type="primary"):
            settings_data = {
                "min_posts_per_day":    posts_range[0],
                "max_posts_per_day":    posts_range[1],
                "min_scrape_interval":  scrape_range[0],
                "max_scrape_interval":  scrape_range[1],
                "min_post_interval":    post_range[0],
                "max_post_interval":    post_range[1],
            }
            
            result = api_request("/config", "PUT", settings_data)
            if result and result.get("success"):
                st.success("Settings saved successfully")
                st.rerun()
            else:
                st.error("Failed to save settings")

elif page == "Facebook":
    st.title("Facebook Integration")
    st.caption("Manage your Facebook page connection and posting settings")

    config_data = api_request("/config")
    current_config = config_data.get("config", {}) if config_data else {}

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Get Permanent Token")
        st.caption("Paste a short-lived token and your app credentials — the app will exchange it for a permanent page token automatically.")

        tab_auto, tab_manual = st.tabs(["Auto Exchange (Recommended)", "Paste Token Manually"])

        with tab_auto:
            st.caption("**Step 1:** Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/) → generate a short-lived User Access Token with `pages_manage_posts` and `publish_video` permissions.\n\n**Step 2:** Fill in the fields below.")
            ex_page_id    = st.text_input("Page ID", value=current_config.get("FACEBOOK_PAGE_ID", ""), key="ex_page_id")
            ex_app_id     = st.text_input("App ID", key="ex_app_id", placeholder="Your Facebook App ID")
            ex_app_secret = st.text_input("App Secret", key="ex_app_secret", type="password", placeholder="Your Facebook App Secret")
            ex_token      = st.text_area("Short-lived User Access Token", key="ex_token", height=80, placeholder="Paste the token from Graph API Explorer")

            if st.button("Exchange & Save Permanent Token", type="primary", use_container_width=True):
                if not all([ex_page_id, ex_app_id, ex_app_secret, ex_token]):
                    st.error("All fields are required")
                else:
                    with st.spinner("Exchanging token with Facebook..."):
                        result = api_request(
                            f"/facebook/exchange-token?short_lived_token={ex_token}&app_id={ex_app_id}&app_secret={ex_app_secret}&page_id={ex_page_id}",
                            "POST"
                        )
                    if result and result.get("success"):
                        st.success(f"{result.get('message')}")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"Failed: {result}")

        with tab_manual:
            st.caption("Paste a token you already know is permanent (e.g. from Business Manager System User).")
            new_page_id = st.text_input("Facebook Page ID", value=current_config.get("FACEBOOK_PAGE_ID", ""), key="fb_page_id")
            new_token   = st.text_area("Page Access Token", value="", height=100, key="fb_token")
            if st.button("Save Token", type="primary", use_container_width=True):
                if not new_token.strip():
                    st.error("Token cannot be empty")
                else:
                    result = api_request("/config", "PUT", {
                        "facebook_page_id": new_page_id,
                        "facebook_access_token": new_token.strip()
                    })
                    if result and result.get("success"):
                        st.success("Token saved")
                        st.rerun()
                    else:
                        st.error("Failed to save")

    with col2:
        st.subheader("Connection Status")

        fb_stats = api_request("/facebook/stats")
        if fb_stats and fb_stats.get("success") and "page_name" in fb_stats:
            st.success("Token is valid")
            st.write(f"**Page:** {fb_stats.get('page_name', 'Unknown')}")
            st.write(f"**Username:** @{fb_stats.get('username', 'Unknown')}")
            st.write(f"**Followers:** {format_number(fb_stats.get('followers', 0))}")
        else:
            st.error("Token expired or invalid — update credentials on the left")

        st.subheader("Recent Post Errors")
        logs = api_request("/logs?limit=50")
        if logs and logs.get("success"):
            errors = [l for l in logs["logs"] if l.get("type") in ("error","warning") and "poster" in l.get("message","").lower() or "token" in l.get("message","").lower()][:5]
            if errors:
                for e in errors:
                    st.caption(f"{e['created_at'][:16]} — {e['message'][:120]}")
            else:
                st.info("No recent posting errors")

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("### PostPilot")
st.sidebar.markdown("Automated TikTok video collection and Facebook posting system")
st.sidebar.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

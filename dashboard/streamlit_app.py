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
    page_title="TikTok Video Collector Dashboard",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
.metric-container {
    background-color: #f0f2f6;
    border: 1px solid #e0e0e0;
    padding: 1rem;
    border-radius: 0.5rem;
    margin: 0.5rem 0;
}
.status-running {
    color: #00c851;
    font-weight: bold;
}
.status-error {
    color: #ff4444;
    font-weight: bold;
}
.status-warning {
    color: #ffbb33;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

# Helper functions
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

# Sidebar
st.sidebar.title("🎯 TikTok Collector")
st.sidebar.markdown("---")

# Navigation
page = st.sidebar.selectbox(
    "Navigate to",
    ["Dashboard", "Keywords", "Videos", "Tasks", "Logs", "Settings", "Facebook"]
)

# Health check in sidebar
with st.sidebar.expander("System Health", expanded=False):
    health = api_request("/health")
    if health:
        st.markdown(f"""
        <div class="status-{get_status_color(health.get('status', 'unknown'))}">
            Status: {health.get('status', 'Unknown').upper()}
        </div>
        """, unsafe_allow_html=True)
        
        st.write(f"**Database:** {health.get('database', 'Unknown')}")
        st.write(f"**Redis:** {health.get('redis', 'Unknown')}")
        st.write(f"**Time:** {health.get('timestamp', 'Unknown')}")

# Main content
if page == "Dashboard":
    st.title("📊 System Dashboard")
    
    # Get system stats
    stats = api_request("/stats")
    if stats and stats.get("success"):
        db_stats = stats.get("database", {})
        
        # Metrics row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="metric-container">
                <h3>{format_number(db_stats.get('overall', {}).get('total_videos', 0))}</h3>
                <p>Total Videos</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="metric-container">
                <h3>{format_number(db_stats.get('today', {}).get('downloaded', 0))}</h3>
                <p>Downloaded Today</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="metric-container">
                <h3>{format_number(db_stats.get('today', {}).get('posted', 0))}</h3>
                <p>Posted Today</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
            <div class="metric-container">
                <h3>{format_number(db_stats.get('overall', {}).get('keywords', 0))}</h3>
                <p>Active Keywords</p>
            </div>
            """, unsafe_allow_html=True)
        
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
    st.title("🔍 Keywords Management")
    
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
    st.title("📹 Videos Management")
    
    # Tabs for different video views
    tab1, tab2, tab3, tab4 = st.tabs(["Pending Downloads", "Pending Posts", "All Videos", "Task Status"])
    
    with tab1:
        st.subheader("Videos Pending Download")
        
        pending_downloads = api_request("/videos/pending-download?limit=50")
        if pending_downloads and pending_downloads.get("success"):
            videos = pending_downloads.get("videos", [])
            
            if videos:
                for i, video in enumerate(videos):
                    with st.expander(f"Video {i+1}: {video.get('tiktok_id', 'Unknown')}"):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**TikTok ID:** {video.get('tiktok_id', 'Unknown')}")
                            st.write(f"**Author:** {video.get('author', 'Unknown')}")
                            st.write(f"**Caption:** {video.get('caption', 'No caption')[:100]}...")
                            st.write(f"**Hashtags:** {', '.join(video.get('hashtags', []))}")
                        
                        with col2:
                            if st.button(f"Download Now", key=f"download_{video.get('tiktok_id')}"):
                                # This would trigger download task
                                st.info("Download task queued")
            else:
                st.info("No videos pending download")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Download All Pending", type="primary"):
                result = api_request("/tasks/download-pending", "POST")
                if result and result.get("success"):
                    st.success(result.get("message", "Download task queued"))
        with col_btn2:
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
    
    with tab2:
        st.subheader("Videos Pending Posting")
        
        pending_posts = api_request("/videos/pending-post?limit=15")
        if pending_posts and pending_posts.get("success"):
            videos = pending_posts.get("videos", [])
            
            if videos:
                for i, video in enumerate(videos):
                    with st.expander(f"Video {i+1}: {video.get('tiktok_id', 'Unknown')}"):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**TikTok ID:** {video.get('tiktok_id', 'Unknown')}")
                            st.write(f"**Author:** {video.get('author', 'Unknown')}")
                            st.write(f"**Caption:** {video.get('caption', 'No caption')[:100]}...")
                            st.write(f"**Hashtags:** {', '.join(video.get('hashtags', []))}")
                        
                        with col2:
                            if st.button(f"Post Now", key=f"post_{video.get('tiktok_id')}"):
                                # This would trigger posting task
                                st.info("Posting task queued")
            else:
                st.info("No videos pending posting")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Post All Pending", type="primary"):
                result = api_request("/tasks/post-pending", "POST")
                if result and result.get("success"):
                    st.success(result.get("message", "Posting task queued"))
        with col_btn2:
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
                rows = []
                for v in videos:
                    rows.append({
                        "TikTok ID": v.get("tiktok_id", ""),
                        "Author": v.get("author", ""),
                        "Caption": (v.get("caption") or "")[:60],
                        "Downloaded": "✅" if v.get("downloaded") else "❌",
                        "Posted": "✅" if v.get("posted") else "❌",
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
                with st.expander(f"📋 {qname.title()} Queue"):
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
    st.title("⚙️ Task Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Manual Tasks")
        
        if st.button("🔍 Scrape All Keywords", type="primary"):
            result = api_request("/tasks/scrape-all", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Scraping task queued"))
            else:
                st.error("Failed to queue scraping task")
        
        if st.button("⬇️ Download Pending Videos"):
            result = api_request("/tasks/download-pending", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Download task queued"))
            else:
                st.error("Failed to queue download task")
        
        if st.button("📤 Post Pending Videos"):
            result = api_request("/tasks/post-pending", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Posting task queued"))
            else:
                st.error("Failed to queue posting task")
        
        if st.button("🧹 Cleanup Old Files"):
            result = api_request("/tasks/cleanup", "POST")
            if result and result.get("success"):
                st.success(result.get("message", "Cleanup task queued"))
            else:
                st.error("Failed to queue cleanup task")
    
    with col2:
        st.subheader("Task Queue Status")
        
        stats = api_request("/stats")
        if stats and stats.get("success") and stats.get("queue"):
            queue_data = stats.get("queue", {})
            
            st.metric("Pending Jobs", queue_data.get("pending_jobs", 0))
            st.metric("Failed Jobs", queue_data.get("failed_jobs", 0))
            st.metric("Scheduled Jobs", queue_data.get("scheduled_jobs", 0))
            st.metric("Started Jobs", queue_data.get("started_jobs", 0))
        else:
            st.info("Queue status not available")

elif page == "Logs":
    st.title("📋 System Logs")
    
    # Log filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        log_limit = st.selectbox("Show last", [50, 100, 200, 500], index=1)
    
    with col2:
        log_type = st.selectbox("Log type", ["All", "info", "error", "warning"])
    
    with col3:
        if st.button("🔄 Refresh"):
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
                    st.markdown(f"🔴 **{log_type_display}** - **{component}**")
                elif "warning" in log.get("type", "").lower():
                    st.markdown(f"🟡 **{log_type_display}** - **{component}**")
                else:
                    st.markdown(f"🟢 **{log_type_display}** - **{component}**")
                
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
    st.title("⚙️ System Settings")
    
    # Get current config
    config_data = api_request("/config")
    if config_data and config_data.get("success"):
        current_config = config_data.get("config", {})
        
        st.subheader("System Configuration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            max_posts = st.number_input(
                "Max Posts Per Day",
                min_value=1,
                max_value=50,
                value=current_config.get("MAX_POSTS_PER_DAY", 15)
            )
            
            scrape_interval = st.number_input(
                "Scrape Interval (minutes)",
                min_value=5,
                max_value=1440,
                value=current_config.get("SCRAPE_INTERVAL", 30)
            )
        
        with col2:
            post_interval = st.number_input(
                "Post Interval (minutes)",
                min_value=15,
                max_value=1440,
                value=current_config.get("POST_INTERVAL", 60)
            )
        
        if st.button("💾 Save Settings", type="primary"):
            settings_data = {
                "max_posts_per_day": max_posts,
                "scrape_interval": scrape_interval,
                "post_interval": post_interval
            }
            
            result = api_request("/config", "PUT", settings_data)
            if result and result.get("success"):
                st.success("Settings saved successfully")
                st.rerun()
            else:
                st.error("Failed to save settings")

elif page == "Facebook":
    st.title("📘 Facebook Integration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Facebook Page Stats")
        
        fb_stats = api_request("/facebook/stats")
        if fb_stats and fb_stats.get("success"):
            if "page_name" in fb_stats:
                st.write(f"**Page Name:** {fb_stats.get('page_name', 'Unknown')}")
                st.write(f"**Username:** @{fb_stats.get('username', 'Unknown')}")
                st.write(f"**Followers:** {format_number(fb_stats.get('followers', 0))}")
                st.write(f"**Talking About:** {format_number(fb_stats.get('talking_about', 0))}")
            else:
                st.info("Facebook stats task queued - check back later")
        else:
            st.warning("Facebook credentials not configured or API error")
    
    with col2:
        st.subheader("Configuration Status")
        
        # Check environment variables (these would be secrets in production)
        if st.secrets.get("FACEBOOK_PAGE_ID") and st.secrets.get("FACEBOOK_ACCESS_TOKEN"):
            st.markdown("🟢 **Facebook credentials configured**")
        else:
            st.markdown("🔴 **Facebook credentials missing**")
            st.info("Please configure Facebook credentials in Streamlit secrets")
        
        st.markdown("---")
        st.write("**Required:**")
        st.write("- Facebook Page ID")
        st.write("- Facebook Access Token")
        st.write("- Page must have video posting permissions")

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("### 🚀 TikTok Video Collector")
st.sidebar.markdown("Automated TikTok video collection and Facebook posting system")
st.sidebar.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

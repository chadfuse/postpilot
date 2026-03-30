"""Bulk keyword addition via text area"""
import streamlit as st
from typing import List, Tuple

def parse_bulk_keywords(text: str) -> Tuple[List[str], List[str]]:
    """Parse keywords from text area
    
    Returns:
        (valid_keywords, invalid_keywords)
    """
    if not text.strip():
        return [], []
    
    # Split by lines and clean up
    lines = text.strip().split('\n')
    keywords = []
    
    for line in lines:
        # Remove extra whitespace and skip empty lines
        keyword = line.strip()
        if keyword:
            keywords.append(keyword)
    
    # Validate keywords
    valid_keywords = []
    invalid_keywords = []
    
    for keyword in keywords:
        # Check length
        if len(keyword) > 100:
            invalid_keywords.append(keyword)
            continue
        
        # Check for valid characters (basic validation)
        if any(char in keyword for char in ['\n', '\r', '\t']):
            invalid_keywords.append(keyword)
            continue
        
        valid_keywords.append(keyword)
    
    # Remove duplicates
    original_count = len(valid_keywords)
    valid_keywords = list(dict.fromkeys(valid_keywords))  # Preserve order
    duplicates_removed = original_count - len(valid_keywords)
    
    if duplicates_removed > 0:
        st.info(f"Removed {duplicates_removed} duplicate keywords")
    
    return valid_keywords, invalid_keywords

def render_bulk_input_section() -> List[str]:
    """Render bulk keyword input section
    
    Returns:
        List of keywords to add, or empty list if not submitted
    """
    st.subheader("📝 Add Multiple Keywords")
    
    # Instructions
    with st.expander("How to use", expanded=False):
        st.markdown("""
        **Instructions:**
        - Enter one keyword per line
        - Maximum 100 characters per keyword
        - Duplicates will be automatically removed
        - Invalid keywords will be skipped
        
        **Example:**
        ```
        football
        basketball
        soccer
        tennis
        ```
        """)
    
    # Text area for bulk input
    bulk_text = st.text_area(
        "Enter keywords (one per line):",
        height=200,
        placeholder="football\nbasketball\nsoccer\ntennis\n...",
        help="Enter one keyword per line. Duplicates will be removed automatically."
    )
    
    if not bulk_text.strip():
        return []
    
    # Parse and validate
    valid_keywords, invalid_keywords = parse_bulk_keywords(bulk_text)
    
    # Show validation results
    if valid_keywords or invalid_keywords:
        st.markdown("---")
        st.subheader("📊 Preview")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if valid_keywords:
                st.success(f"✅ Valid Keywords ({len(valid_keywords)})")
                for keyword in valid_keywords[:10]:  # Show first 10
                    st.code(keyword)
                if len(valid_keywords) > 10:
                    st.info(f"... and {len(valid_keywords) - 10} more")
            else:
                st.info("No valid keywords found")
        
        with col2:
            if invalid_keywords:
                st.error(f"❌ Invalid Keywords ({len(invalid_keywords)})")
                for keyword in invalid_keywords[:5]:  # Show first 5
                    st.code(keyword)
                if len(invalid_keywords) > 5:
                    st.info(f"... and {len(invalid_keywords) - 5} more")
                
                st.caption("Invalid keywords are too long or contain unsupported characters")
    
    # Add button
    if valid_keywords:
        st.markdown("---")
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button(f"✅ Add {len(valid_keywords)} Keywords", type="primary", use_container_width=True):
                return valid_keywords
        
        with col2:
            if st.button("❌ Clear", use_container_width=True):
                st.rerun()
    
    return []

def add_keywords_bulk(keywords: List[str], api_request_func) -> Tuple[int, int, List[str]]:
    """Add multiple keywords to the system
    
    Returns:
        (success_count, failed_count, failed_keywords)
    """
    success_count = 0
    failed_count = 0
    failed_keywords = []
    
    # Progress bar
    progress_bar = st.progress(0, text="Adding keywords...")
    total_keywords = len(keywords)
    
    for i, keyword in enumerate(keywords):
        try:
            result = api_request_func("/keywords", "POST", {"keyword": keyword})
            if result and result.get("success"):
                success_count += 1
            else:
                failed_count += 1
                failed_keywords.append(keyword)
        except Exception as e:
            failed_count += 1
            failed_keywords.append(keyword)
        
        # Update progress
        progress = (i + 1) / total_keywords
        progress_bar.progress(progress, text=f"Adding keywords... {i + 1}/{total_keywords}")
    
    progress_bar.empty()
    return success_count, failed_count, failed_keywords

def render_bulk_results(success_count: int, failed_count: int, failed_keywords: List[str]):
    """Render bulk addition results"""
    st.markdown("---")
    st.subheader("📈 Results")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("✅ Successful", success_count)
    with col2:
        st.metric("❌ Failed", failed_count)
    with col3:
        total = success_count + failed_count
        st.metric("📊 Total", total)
    
    if failed_keywords:
        st.markdown("---")
        st.subheader("⚠️ Failed Keywords")
        st.write("These keywords couldn't be added:")
        
        # Show failed keywords in columns
        cols = st.columns(min(4, len(failed_keywords)))
        for i, keyword in enumerate(failed_keywords):
            cols[i % 4].code(keyword)
        
        st.info("Common reasons: keyword already exists, too long (>100 chars), or invalid characters")
    
    if success_count > 0:
        st.success(f"Successfully added {success_count} keywords! 🎉")
        st.balloons()
    elif failed_count > 0 and success_count == 0:
        st.warning("No new keywords were added. They may already exist in the system.")

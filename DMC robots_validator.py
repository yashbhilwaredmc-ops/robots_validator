import streamlit as st
import re
import requests
from io import StringIO
import urllib.parse

# Set page configuration
st.set_page_config(
    page_title="DMC Robots.txt Validator",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Core Logic ---
KNOWN_BOTS = [
    "Googlebot", "AdsBot-Google", "AdsBot-Google-Mobile-Apps", "facebookexternalhit",
    "Googlebot-Image", "Mediapartners-Google", "Googlebot-news", "APIs-Google",
    "Googlebot-Video", "AdsBot-Google-Mobile", "Pinterestbot", "Twitterbot",
    "Bingbot", "Slurp", "DuckDuckBot", "Baiduspider", "YandexBot", "Sogou", "Exabot"
]

VALID_DIRECTIVES = [
    "user-agent", "disallow", "allow", "sitemap", "crawl-delay",
    "host", "clean-param", "noindex"
]

# Legitimate user agents for different purposes
LEGITIMATE_USER_AGENTS = {
    'standard_browser': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'googlebot': 'Googlebot/2.1 (+http://www.google.com/bot.html)',
    'bingbot': 'Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)',
    'default_crawler': 'DMC-Robots-Validator/1.0 (+https://github.com/dmc/robots-validator)'
}

def fetch_robots_txt(url, user_agent_type='standard_browser'):
    """Fetch robots.txt with appropriate user agent"""
    headers = {'User-Agent': LEGITIMATE_USER_AGENTS[user_agent_type]}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text, response.status_code, None
    except requests.exceptions.RequestException as e:
        return None, None, str(e)

def validate_robots_txt_content(content):
    lines = content.splitlines()
    issues = []
    agents_seen = []
    sitemap_found = False
    host_found = False
    disallow_count = 0
    allow_count = 0
    user_agent_defined = False
    current_user_agent = None

    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if ':' not in stripped:
            issues.append(f"Line {line_num}: ❌ Missing ':' in directive → `{stripped}`")
            continue

        directive, value = map(str.strip, stripped.split(":", 1))
        lower_directive = directive.lower()

        if lower_directive not in VALID_DIRECTIVES:
            issues.append(f"Line {line_num}: ⚠️ Unknown directive → `{directive}`")

        if lower_directive == "user-agent":
            user_agent_defined = True
            current_user_agent = value
            agents_seen.append(value)
            known = any(bot.lower() in value.lower() for bot in KNOWN_BOTS) or value == "*"
            if not known:
                issues.append(f"Line {line_num}: ⚠️ Possibly unknown user-agent → `{value}`")

        elif lower_directive == "sitemap":
            sitemap_found = True
            if not re.match(r"^https?://", value):
                issues.append(f"Line {line_num}: ❌ Invalid sitemap URL → `{value}`")

        elif lower_directive == "host":
            host_found = True
            if re.findall(r"\s", value):
                issues.append(f"Line {line_num}: ❌ Host should not contain whitespace → `{value}`")

        elif lower_directive == "disallow":
            disallow_count += 1
            if value != '' and not value.startswith("/"):
                issues.append(f"Line {line_num}: ❌ Disallow path must start with '/' or be empty → `{value}`")

        elif lower_directive == "allow":
            allow_count += 1
            if value != '' and not value.startswith("/"):
                issues.append(f"Line {line_num}: ❌ Allow path must start with '/' or be empty → `{value}`")

        elif lower_directive == "crawl-delay":
            try:
                delay = float(value)
                if delay < 0:
                    issues.append(f"Line {line_num}: ❌ Crawl-delay must be non-negative → `{value}`")
            except ValueError:
                issues.append(f"Line {line_num}: ❌ Invalid crawl-delay value → `{value}`")

    # Summary checks
    if not user_agent_defined:
        issues.append("❌ No `User-agent` defined in robots.txt")
    if not sitemap_found:
        issues.append("⚠️ Sitemap is not defined (recommended)")
    if not host_found:
        issues.append("⚠️ Host is not defined (recommended for Yandex)")
    if len(set(agents_seen)) < len(agents_seen):
        issues.append("⚠️ Duplicate user-agent entries found")
    if disallow_count == 0:
        issues.append("⚠️ No `Disallow` rules defined")
    if allow_count == 0:
        issues.append("⚠️ No `Allow` rules defined")

    if not issues:
        return ["✅ All validations passed! Your robots.txt is clean."], True
    return issues, False

def auto_fix_content(content):
    fixed_lines = []
    seen_user_agents = set()
    has_user_agent = False
    has_disallow = False
    has_host = False
    has_sitemap = False

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            fixed_lines.append(stripped)
            continue

        if ':' not in stripped:
            parts = stripped.split()
            if len(parts) == 2:
                directive, value = parts
                fixed_lines.append(f"{directive.strip().capitalize()}: {value.strip()}")
            else:
                fixed_lines.append(f"# ⚠ Unfixable line: {stripped}")
            continue

        directive, value = map(str.strip, stripped.split(":", 1))
        directive_lower = directive.lower()

        if directive_lower == "user agent":
            directive = "user-agent"

        if directive_lower == "user-agent":
            has_user_agent = True
            if value.lower() not in seen_user_agents:
                seen_user_agents.add(value.lower())
                fixed_lines.append(f"User-agent: {value}")
            continue

        elif directive_lower == "allow":
            if value and not value.startswith("/"):
                value = f"/{value}"
            fixed_lines.append(f"Allow: {value}")
            continue

        elif directive_lower == "disallow":
            has_disallow = True
            if value and not value.startswith("/"):
                value = f"/{value}"
            fixed_lines.append(f"Disallow: {value}")
            continue

        elif directive_lower == "host":
            has_host = True
            value = value.replace(" ", "")
            fixed_lines.append(f"Host: {value}")
            continue

        elif directive_lower == "sitemap":
            has_sitemap = True
            if not value.lower().startswith("http"):
                value = f"https://{value}"
            fixed_lines.append(f"Sitemap: {value}")
            continue

        else:
            fixed_lines.append(f"{directive.capitalize()}: {value}")

    # Add missing essential directives
    if not has_user_agent:
        fixed_lines.insert(0, "# Added missing User-agent directive")
        fixed_lines.insert(1, "User-agent: *")
    
    if not has_disallow:
        fixed_lines.append("\n# Added default Disallow rule")
        fixed_lines.append("Disallow:")
    
    if not has_host:
        fixed_lines.append("\n# Added placeholder Host directive")
        fixed_lines.append("# Host: example.com (replace with your actual domain)")
    
    if not has_sitemap:
        fixed_lines.append("\n# Added placeholder Sitemap directive")
        fixed_lines.append("# Sitemap: https://example.com/sitemap.xml (replace with your actual sitemap URL)")

    return "\n".join(fixed_lines)

# --- Streamlit UI ---
st.title("🤖 DMC Robots.txt Validator")
st.markdown("Validate, analyze, and fix robots.txt files for SEO best practices.")

# Initialize session state
if 'validation_results' not in st.session_state:
    st.session_state.validation_results = None
if 'fixed_content' not in st.session_state:
    st.session_state.fixed_content = None

# Sidebar for options
with st.sidebar:
    st.header("Options")
    user_agent_type = st.selectbox(
        "Select User Agent for Fetching",
        options=list(LEGITIMATE_USER_AGENTS.keys()),
        index=0,
        help="Choose which user agent to use when fetching robots.txt files"
    )
    
    st.header("About")
    st.info("""
    This tool helps you:
    - Validate robots.txt syntax
    - Identify common issues
    - Fix problems automatically
    - Test with different user agents
    """)

# Tabs for different input methods
tab1, tab2, tab3 = st.tabs(["Fetch from URL", "Paste Content", "Upload File"])

with tab1:
    st.subheader("Fetch robots.txt from URL")
    url_input = st.text_input("Enter website URL:", placeholder="https://example.com")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Fetch & Validate", type="primary"):
            if url_input:
                # Normalize URL
                if not url_input.startswith(('http://', 'https://')):
                    url_input = 'https://' + url_input
                
                robots_url = urllib.parse.urljoin(url_input, '/robots.txt')
                
                with st.spinner(f"Fetching robots.txt from {robots_url}..."):
                    content, status_code, error = fetch_robots_txt(robots_url, user_agent_type)
                    
                    if error:
                        st.error(f"Error fetching robots.txt: {error}")
                    else:
                        st.session_state.validation_results = validate_robots_txt_content(content)
                        st.session_state.original_content = content
                        st.session_state.source = robots_url
    
    with col2:
        if st.button("Show Raw Content"):
            if 'original_content' in st.session_state:
                st.text_area("Raw robots.txt content", st.session_state.original_content, height=300)

with tab2:
    st.subheader("Paste robots.txt Content")
    pasted_content = st.text_area("Paste your robots.txt content here:", height=200)
    
    if st.button("Validate Pasted Content", type="primary"):
        if pasted_content:
            st.session_state.validation_results = validate_robots_txt_content(pasted_content)
            st.session_state.original_content = pasted_content
            st.session_state.source = "Pasted Content"

with tab3:
    st.subheader("Upload robots.txt File")
    uploaded_file = st.file_uploader("Choose a robots.txt file", type=['txt'])
    
    if uploaded_file is not None:
        content = uploaded_file.getvalue().decode("utf-8")
        if st.button("Validate Uploaded File", type="primary"):
            st.session_state.validation_results = validate_robots_txt_content(content)
            st.session_state.original_content = content
            st.session_state.source = uploaded_file.name

# Display results
if st.session_state.validation_results:
    issues, is_valid = st.session_state.validation_results
    
    st.subheader(f"Validation Results for: {st.session_state.source}")
    
    # Statistics
    total_issues = len(issues)
    error_count = sum(1 for issue in issues if '❌' in issue)
    warning_count = sum(1 for issue in issues if '⚠️' in issue)
    success_count = sum(1 for issue in issues if '✅' in issue)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Issues", total_issues)
    col2.metric("Errors", error_count)
    col3.metric("Warnings", warning_count)
    col4.metric("Success", success_count)
    
    # Display issues
    with st.expander("View Detailed Results", expanded=True):
        for issue in issues:
            if '❌' in issue:
                st.error(issue)
            elif '⚠️' in issue:
                st.warning(issue)
            elif '✅' in issue:
                st.success(issue)
            else:
                st.info(issue)
    
    # Auto-fix option
    if not is_valid:
        st.subheader("Auto-Fix Options")
        if st.button("🛠️ Auto-Fix Issues"):
            fixed_content = auto_fix_content(st.session_state.original_content)
            st.session_state.fixed_content = fixed_content
            
            # Validate fixed content
            fixed_issues, fixed_is_valid = validate_robots_txt_content(fixed_content)
            st.session_state.fixed_results = (fixed_issues, fixed_is_valid)
        
        # Show fixed content if available
        if 'fixed_content' in st.session_state and st.session_state.fixed_content:
            st.subheader("Fixed robots.txt")
            st.text_area("Fixed content", st.session_state.fixed_content, height=300)
            
            # Download option
            st.download_button(
                label="📥 Download Fixed robots.txt",
                data=st.session_state.fixed_content,
                file_name="fixed_robots.txt",
                mime="text/plain"
            )
            
            # Validate fixed version
            if 'fixed_results' in st.session_state:
                fixed_issues, fixed_is_valid = st.session_state.fixed_results
                st.subheader("Fixed Version Validation")
                for issue in fixed_issues:
                    if '❌' in issue:
                        st.error(issue)
                    elif '⚠️' in issue:
                        st.warning(issue)
                    elif '✅' in issue:
                        st.success(issue)

# Footer
st.markdown("---")
st.caption("DMC Robots.txt Validator Tool | Best practices for search engine crawling")

# Instructions for deployment
with st.expander("Deployment Instructions"):
    st.markdown("""
    ## How to Deploy This Tool
    
    1. **Save this code** as `robots_validator.py`
    2. **Create requirements.txt** with:
       ```
       streamlit>=1.22.0
       requests>=2.28.0
       ```
    3. **Test locally**:
       ```bash
       streamlit run robots_validator.py
       ```
    4. **Deploy to Streamlit Cloud**:
       - Create a GitHub repository
       - Upload your files
       - Connect to Streamlit Cloud
       - Deploy!
    """)

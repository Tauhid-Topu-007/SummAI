import streamlit as st
import validators
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import re
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# Page configuration
st.set_page_config(
    page_title="SummAI | Premium Content Summarizer",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #0f0f13 0%, #1a1a24 50%, #0f0f13 100%);
        font-family: 'Inter', sans-serif;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .main-title {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(90deg, #a78bfa, #60a5fa, #34d399);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.3rem;
    }
    
    .subtitle {
        text-align: center;
        color: #94a3b8;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    .summary-card {
        background: linear-gradient(145deg, rgba(30, 30, 46, 0.9), rgba(20, 20, 35, 0.95));
        border: 1px solid rgba(96, 165, 250, 0.25);
        border-radius: 16px;
        padding: 2rem;
        margin-top: 1.5rem;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
    }
    
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #12121a 0%, #1a1a28 100%);
        border-right: 1px solid rgba(139, 92, 246, 0.15);
    }
    
    .stTextInput > div > div > input {
        background-color: rgba(20, 20, 35, 0.8) !important;
        border: 1px solid rgba(139, 92, 246, 0.3) !important;
        border-radius: 10px !important;
        color: #f1f5f9 !important;
        padding: 0.75rem 1rem !important;
    }
    
    .stButton > button {
        background: linear-gradient(90deg, #7c3aed, #4f46e5) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.75rem 2rem !important;
        font-weight: 600 !important;
        width: 100%;
        box-shadow: 0 4px 15px rgba(124, 58, 237, 0.4) !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(90deg, #6d28d9, #4338ca) !important;
        transform: translateY(-2px);
    }
    
    .feature-badge {
        display: inline-block;
        background: rgba(139, 92, 246, 0.15);
        color: #c4b5fd;
        padding: 0.35rem 0.85rem;
        border-radius: 20px;
        font-size: 0.85rem;
        margin: 0.25rem;
        border: 1px solid rgba(139, 92, 246, 0.25);
    }
    
    .footer {
        text-align: center;
        color: #64748b;
        font-size: 0.85rem;
        margin-top: 3rem;
        padding-top: 1.5rem;
        border-top: 1px solid rgba(139, 92, 246, 0.1);
    }
</style>
""", unsafe_allow_html=True)


def extract_youtube_id(url: str):
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def load_youtube_transcript(url: str):
    video_id = extract_youtube_id(url)
    if not video_id:
        raise ValueError("Could not extract YouTube video ID from the URL.")

    try:
        ytt_api = YouTubeTranscriptApi()
        try:
            fetched = ytt_api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        except NoTranscriptFound:
            transcript_list = ytt_api.list(video_id)
            fetched = None
            for t in transcript_list:
                fetched = t.fetch()
                break
            if fetched is None:
                raise NoTranscriptFound(video_id)

        texts = []
        for snippet in fetched:
            if hasattr(snippet, "text"):
                texts.append(snippet.text)
            elif isinstance(snippet, dict):
                texts.append(snippet.get("text", ""))
            else:
                texts.append(str(snippet))

        text = " ".join(texts).strip()
        if not text:
            raise ValueError("Transcript is empty.")

        return [Document(page_content=text, metadata={"source": url, "video_id": video_id})]

    except TranscriptsDisabled:
        raise ValueError("This video has transcripts disabled.")
    except NoTranscriptFound:
        raise ValueError("No transcript found for this video. Try a video that has captions enabled.")
    except Exception as e:
        raise ValueError(f"Failed to fetch YouTube transcript: {str(e)}")


def load_website_content(url: str):
    """Simple, reliable website content loader without langchain-community."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()
    except Exception as e:
        raise ValueError(f"Could not fetch the website: {str(e)}")

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()

    # Prefer main/article content if present
    main = soup.find("main") or soup.find("article") or soup.find("div", {"role": "main"}) or soup.body
    if main is None:
        main = soup

    text = main.get_text(separator="\n", strip=True)
    # Clean excessive newlines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    if not text or len(text) < 50:
        raise ValueError("Could not extract meaningful text from the website.")

    return [Document(page_content=text, metadata={"source": url})]


# Session state for history
if "history" not in st.session_state:
    st.session_state.history = []

# Header
st.markdown('<h1 class="main-title">✨ SummAI</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Premium AI-powered summarizer for YouTube videos & websites</p>', unsafe_allow_html=True)

st.markdown("""
<div style="text-align: center; margin-bottom: 2rem;">
    <span class="feature-badge">⚡ Groq Lightning Fast</span>
    <span class="feature-badge">🎥 YouTube Support</span>
    <span class="feature-badge">🌐 Any Website</span>
    <span class="feature-badge">🧠 Smart Chunking</span>
    <span class="feature-badge">📜 Session History</span>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    st.markdown("---")

    groq_api_key = st.text_input(
        "🔑 Groq API Key",
        type="password",
        placeholder="gsk_...",
        help="Get free key from console.groq.com"
    )

    st.markdown("---")
    st.markdown("### 🤖 Model Selection")
    st.caption("Updated Nov 2026 — free/developer tier models")

    model_options = {
        "GPT-OSS 20B (Fast & Free)": "openai/gpt-oss-20b",
        "GPT-OSS 120B (Best Quality)": "openai/gpt-oss-120b",
        "Qwen3.8 27B (Strong Reasoning)": "qwen/qwen3.8-27b",
    }

    selected_model_label = st.selectbox(
        "Choose Model",
        options=list(model_options.keys()),
        index=0
    )
    selected_model = model_options[selected_model_label]

    st.markdown("---")
    st.markdown("### 📝 Summary Style")

    summary_length = st.select_slider(
        "Target Length",
        options=["Short (100 words)", "Medium (250 words)", "Detailed (400 words)", "Long (600 words)"],
        value="Medium (250 words)"
    )

    length_map = {
        "Short (100 words)": 100,
        "Medium (250 words)": 250,
        "Detailed (400 words)": 400,
        "Long (600 words)": 600,
    }
    target_words = length_map[summary_length]

    st.markdown("---")
    st.markdown("### 📜 Session History")
    if st.session_state.history:
        for i, item in enumerate(reversed(st.session_state.history[-5:])):
            with st.expander(f"{item['time']} · {item['source'][:40]}..."):
                st.write(item["summary"][:300] + "...")
        if st.button("Clear History"):
            st.session_state.history = []
            st.rerun()
    else:
        st.caption("No summaries yet.")

    st.markdown("---")
    st.markdown("""
    <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.6;">
        <strong>How to use:</strong><br>
        1. Enter Groq API key<br>
        2. Paste YouTube / website URL<br>
        3. Click Generate Summary<br><br>
        <strong>Tip:</strong> Videos with captions work best.
    </div>
    """, unsafe_allow_html=True)

# Main content
col1, col2, col3 = st.columns([1, 6, 1])

with col2:
    generic_url = st.text_input(
        "🔗 Enter URL (YouTube video or Website)",
        placeholder="https://www.youtube.com/watch?v=... or https://example.com/article",
    )

    with st.expander("📌 Example URLs"):
        st.code("https://www.youtube.com/watch?v=dQw4w9WgXcQ", language=None)
        st.code("https://en.wikipedia.org/wiki/Artificial_intelligence", language=None)

    generate_btn = st.button("🚀 Generate Summary", use_container_width=True)

if generate_btn:
    if not groq_api_key or not groq_api_key.strip():
        st.error("⚠️ Please enter your Groq API Key in the sidebar.")
    elif not generic_url or not generic_url.strip():
        st.error("⚠️ Please enter a valid URL.")
    elif not validators.url(generic_url):
        st.error("⚠️ Invalid URL. Use full URL starting with http:// or https://")
    else:
        try:
            with st.spinner("🔄 Fetching content & generating summary..."):
                start_time = time.time()

                is_youtube = "youtube.com" in generic_url or "youtu.be" in generic_url

                if is_youtube:
                    docs = load_youtube_transcript(generic_url)
                    source_type = "YouTube Video"
                else:
                    docs = load_website_content(generic_url)
                    source_type = "Website"

                if not docs or not docs[0].page_content.strip():
                    st.error("❌ Could not extract content. Page may be empty or blocked.")
                    st.stop()

                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=3500,
                    chunk_overlap=200
                )
                split_docs = text_splitter.split_documents(docs)

                llm = ChatGroq(
                    model=selected_model,
                    groq_api_key=groq_api_key,
                    temperature=0.3
                )

                full_text = "\n\n".join([doc.page_content for doc in split_docs])
                if len(full_text) > 14000:
                    full_text = full_text[:14000] + "\n\n[Content truncated...]"

                prompt_template = f"""You are an expert content summarizer. Provide a clear, well-structured, and informative summary of the following content in approximately {target_words} words.

Guidelines:
- Capture the main ideas, key points, and important details
- Use natural, professional language
- Organize into coherent paragraphs
- Avoid fluff
- If it is a video transcript, summarize the spoken content accurately

Content:
{{text}}

Summary:"""

                prompt = PromptTemplate.from_template(prompt_template)
                final_prompt = prompt.format(text=full_text)

                response = llm.invoke(final_prompt)

                if hasattr(response, "content"):
                    summary_text = response.content
                else:
                    summary_text = str(response)

                elapsed = round(time.time() - start_time, 1)

                # Save to history
                st.session_state.history.append({
                    "time": datetime.now().strftime("%H:%M"),
                    "source": generic_url,
                    "summary": summary_text,
                    "model": selected_model_label,
                    "type": source_type,
                })

                st.markdown("---")

                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.metric("Source", source_type)
                with m2:
                    st.metric("Model", selected_model_label.split("(")[0].strip())
                with m3:
                    st.metric("Time", f"{elapsed}s")
                with m4:
                    st.metric("Words (approx)", len(summary_text.split()))

                st.markdown("### 📄 Generated Summary")
                st.markdown(f"""
                <div class="summary-card">
                    <p style="color: #e2e8f0; font-size: 1.05rem; line-height: 1.75; margin: 0;">
                        {summary_text}
                    </p>
                </div>
                """, unsafe_allow_html=True)

                st.download_button(
                    label="📥 Download Summary as TXT",
                    data=summary_text,
                    file_name=f"summary_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

                st.success("✅ Summary generated successfully!")

        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "authentication" in error_msg.lower() or ("invalid" in error_msg.lower() and "key" in error_msg.lower()):
                st.error("❌ Invalid or missing Groq API Key.")
            elif "rate limit" in error_msg.lower() or "429" in error_msg:
                st.error("❌ Rate limit exceeded. Wait a moment and try again.")
            elif "model" in error_msg.lower() and ("not exist" in error_msg.lower() or "decommissioned" in error_msg.lower() or "not_found" in error_msg.lower()):
                st.error("❌ Model not available on your Groq account. Try GPT-OSS 20B or GPT-OSS 120B.")
            elif "transcript" in error_msg.lower() or "caption" in error_msg.lower():
                st.error(f"❌ {error_msg}")
            else:
                st.error(f"❌ An error occurred: {error_msg}")
                with st.expander("Technical details"):
                    st.exception(e)

st.markdown("""
<div class="footer">
    Built with ❤️ using Streamlit · LangChain<br>
    Models updated for Nov 2026 free/developer tier · No deprecated packages
</div>
""", unsafe_allow_html=True)

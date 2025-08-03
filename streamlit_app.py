import streamlit as st
import nltk

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api.formatters import TextFormatter
from yt_dlp import YoutubeDL
from rake_nltk import Rake
from urllib.parse import urlparse, parse_qs

# 📌 Download NLTK data on demand
def ensure_nltk_ready():
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords", quiet=True)

# 🔗 Support multiple YouTube link formats
def get_video_id(url):
    if "youtube.com" in url:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get("v", [None])[0]
    elif "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    return None

# 🎬 Get transcript
def extract_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        formatter = TextFormatter()
        return formatter.format_transcript(transcript)
    except (NoTranscriptFound, TranscriptsDisabled):
        return "⚠️ Transcript not available for this video."
    except VideoUnavailable:
        return "❌ This video is unavailable."
    except Exception as e:
        return f"🚨 Error retrieving transcript: {str(e)}"

# 🧠 Extract keywords
def extract_keywords(text, num=10):
    ensure_nltk_ready()
    rake = Rake()
    rake.extract_keywords_from_text(text)
    return rake.get_ranked_phrases()[:num]

# 📊 Get video metadata
def get_metadata(url):
    ydl_opts = {'quiet': True, 'skip_download': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            "Title": info.get("title"),
            "Views": info.get("view_count"),
            "Length (sec)": info.get("duration"),
            "Publish Date": info.get("upload_date"),
            "Description": info.get("description", "")[:300] + "..." if info.get("description") else "No description available"
        }

# 🌙 Dark mode styling
st.set_page_config(page_title="YouTube Transcript + SEO Tool", layout="centered")

st.markdown("""
    <style>
    body {
        background-color: #0e1117;
        color: #ffffff;
    }
    .stTextInput > div > div > input,
    .stTextArea textarea {
        background-color: #1e222a;
        color: white;
    }
    .stTextInput label, .stTextArea label {
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# 🧩 App interface
st.title("📺 YouTube Transcript + SEO Info")

with st.form("url_form"):
    url = st.text_input("Enter YouTube Video URL")
    submitted = st.form_submit_button("Get Video Info")

if submitted and url:
    video_id = get_video_id(url)

    if not video_id:
        st.error("Invalid YouTube URL")
    else:
        st.subheader("🔍 Video Metadata")
        metadata = get_metadata(url)
        for k, v in metadata.items():
            st.markdown(f"**{k}**: {v}")

        st.subheader("🧠 Top Keywords")
        transcript = extract_transcript(video_id)
        keywords = extract_keywords(transcript)
        st.write(", ".join(keywords))

        st.subheader("📝 Transcript")
        st.text_area("Copyable Transcript", transcript, height=400)

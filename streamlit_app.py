import streamlit as st
import nltk

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from yt_dlp import YoutubeDL
from rake_nltk import Rake
from urllib.parse import urlparse, parse_qs

# 💡 Ensure NLTK resources are available
def ensure_nltk_ready():
    for resource in ["punkt", "stopwords"]:
        try:
            nltk.data.find(f"tokenizers/{resource}" if resource == "punkt" else f"corpora/{resource}")
        except LookupError:
            nltk.download(resource, quiet=True)

# 🔗 Extract video ID
def get_video_id(url):
    if "youtube.com" in url:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get("v", [None])[0]
    elif "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    return None

# 📜 Get transcript (if available)
def extract_transcript(video_id):
    try:
        # Based on the actual youtube-transcript-api, the correct pattern is:
        # YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        # But since get_transcript doesn't exist, let's try the static method approach
        
        try:
            # Try the most common working pattern for this API
            from youtube_transcript_api import YouTubeTranscriptApi as YTAPI
            transcript_list = YTAPI.get_transcript(video_id, languages=['en', 'en-US'])
            formatter = TextFormatter()
            return formatter.format_transcript(transcript_list)
        except AttributeError:
            # If get_transcript doesn't work, try alternative import pattern
            try:
                from youtube_transcript_api.api import YouTubeTranscriptApi as API
                transcript_list = API.get_transcript(video_id)
                formatter = TextFormatter()
                return formatter.format_transcript(transcript_list)
            except (ImportError, AttributeError):
                # Last resort: try the fetch method with correct signature
                try:
                    # Maybe fetch is an instance method
                    api_instance = YouTubeTranscriptApi()
                    transcript_list = api_instance.fetch(video_id)
                    formatter = TextFormatter()
                    return formatter.format_transcript(transcript_list)
                except:
                    return "🚨 Unable to retrieve transcript with any available method. The API may have changed significantly."
            
    except Exception as e:
        return f"🚨 Error retrieving transcript: {str(e)}"

# 🧠 Extract keywords
def extract_keywords(text, num=10):
    ensure_nltk_ready()
    rake = Rake()
    rake.extract_keywords_from_text(text)
    return rake.get_ranked_phrases()[:num]

# 📊 Get metadata with yt-dlp
def get_metadata(url):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'nocheckcertificate': True
    }

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

# 🎛️ App UI
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

        if keywords:
            st.write(", ".join(keywords))
        else:
            st.info("No keywords found in this transcript.")

        st.subheader("📝 Transcript")
        st.text_area("Copyable Transcript", transcript, height=400)

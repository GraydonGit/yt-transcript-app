import streamlit as st
import nltk
nltk.download("stopwords", quiet=True)
nltk.download("punkt", quiet=True)

# Force-load the tokenizer (prevents weird 'punkt_tab' errors)
from nltk.tokenize import sent_tokenize
sent_tokenize("Just initializing punkt.")

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api.formatters import TextFormatter
from yt_dlp import YoutubeDL
from rake_nltk import Rake
import re
from urllib.parse import urlparse, parse_qs

def get_video_id(url):
    try:
        # Handle full YouTube URL (watch?v=...)
        if "youtube.com" in url:
            parsed_url = urlparse(url)
            query = parse_qs(parsed_url.query)
            return query["v"][0] if "v" in query else None
        # Handle short youtu.be link
        elif "youtu.be" in url:
            return url.split("/")[-1].split("?")[0]
    except Exception:
        return None

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

def extract_keywords(text, num=10):
    rake = Rake()
    rake.extract_keywords_from_text(text)
    return rake.get_ranked_phrases()[:num]

def get_metadata(url):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
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

st.set_page_config(page_title="YouTube Transcript + SEO Tool", layout="centered")
st.title("📺 YouTube Transcript + SEO Info")

url = st.text_input("Enter YouTube Video URL")

if url:
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

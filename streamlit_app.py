import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from youtube_transcript_api.formatters import TextFormatter
from pytube import YouTube
from rake_nltk import Rake
import re

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
    except TranscriptsDisabled:
        return "Transcript not available for this video."

def extract_keywords(text, num=10):
    rake = Rake()
    rake.extract_keywords_from_text(text)
    return rake.get_ranked_phrases()[:num]

def get_metadata(url):
    yt = YouTube(url)
    return {
        "Title": yt.title,
        "Views": yt.views,
        "Length (sec)": yt.length,
        "Publish Date": yt.publish_date,
        "Description": yt.description[:300] + "..." if yt.description else "No description available"
    }

st.set_page_config(page_title="YouTube Transcript & SEO Tool", layout="centered")
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

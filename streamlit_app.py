import re
import streamlit as st
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable
)
from youtube_transcript_api.formatters import (
    TextFormatter, SRTFormatter, JSONFormatter
)

# --- small helpers -----------------------------------------------------------
def extract_video_id(url_or_id: str) -> str:
    """
    Accepts a full YouTube URL or a naked 11-char video ID
    and always returns the ID.
    """
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url_or_id)
    return match.group(1) if match else url_or_id.strip()

@st.cache_data(show_spinner=False)
def fetch_transcript(video_id: str, langs: list[str]):
    # youtube-transcript-api prefers 'en' first if you give no list
    return YouTubeTranscriptApi().fetch(video_id, languages=langs)  # :contentReference[oaicite:1]{index=1}
# -----------------------------------------------------------------------------

st.title("YouTube Transcript Viewer")

url = st.text_input("Paste a YouTube link or video ID")
lang_order = st.text_input("Preferred languages (comma separated)", "en")
langs = [l.strip() for l in lang_order.split(",") if l.strip()]

if st.button("Get transcript") and url:
    vid = extract_video_id(url)
    with st.spinner("Fetching transcript…"):
        try:
            raw = fetch_transcript(vid, langs)
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as err:
            st.error(f"Could not fetch transcript: {err}")
        else:
            txt = TextFormatter().format_transcript(raw)
            st.text_area("Transcript", txt, height=400)

            # download buttons
            st.download_button("Download .txt", txt, f"{vid}.txt")
            st.download_button(
                "Download .srt",
                SRTFormatter().format_transcript(raw),
                f"{vid}.srt"
            )
            st.download_button(
                "Download .json",
                JSONFormatter().format_transcript(raw),
                f"{vid}.json"
            )

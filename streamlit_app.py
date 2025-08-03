import re
import streamlit as st
import importlib.metadata
from youtube_transcript_api._api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter, SRTFormatter, JSONFormatter
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

# --- Utilities ----------------------------------------------------------------
def extract_video_id(url_or_id: str) -> str:
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url_or_id)
    return match.group(1) if match else url_or_id.strip()

@st.cache_data(show_spinner=False)
def fetch_transcript(video_id: str, langs: list[str]):
    return YouTubeTranscriptApi.get_transcript(video_id, languages=langs)

@st.cache_data(show_spinner=False)
def list_available_transcripts(video_id: str):
    return YouTubeTranscriptApi.list_transcripts(video_id)
# ------------------------------------------------------------------------------

# Version info
st.write("youtube-transcript-api version:", importlib.metadata.version("youtube-transcript-api"))

# UI
st.title("🎞️ YouTube Transcript Viewer")

url = st.text_input("Paste a YouTube link or video ID")
lang_order = st.text_input("Preferred languages (comma-separated)", "en")
langs = [l.strip() for l in lang_order.split(",") if l.strip()]

if url:
    vid = extract_video_id(url)
    st.markdown(f"🎯 **Extracted Video ID:** `{vid}`")

    with st.expander("🔍 Show available transcripts"):
        try:
            transcripts = list_available_transcripts(vid)
            for t in transcripts:
                st.write(f"- **{t.language}** | {'Generated' if t.is_generated else 'Manual'} | Translatable: {t.is_translatable}")
        except Exception as e:
            st.error(f"❌ Error fetching transcript list: {e}")

    if st.button("📜 Get Transcript"):
        with st.spinner("Fetching transcript…"):
            try:
                raw = fetch_transcript(vid, langs)
                txt = TextFormatter().format_transcript(raw)

                st.text_area("Transcript", txt, height=400)

                # Downloads
                st.download_button("⬇️ Download .txt", txt, f"{vid}.txt")
                st.download_button("⬇️ Download .srt", SRTFormatter().format_transcript(raw), f"{vid}.srt")
                st.download_button("⬇️ Download .json", JSONFormatter().format_transcript(raw), f"{vid}.json")

            except TranscriptsDisabled:
                st.error("🚫 Transcripts are disabled for this video.")
            except NoTranscriptFound:
                st.error("🚫 No transcript found for the selected languages.")
            except VideoUnavailable:
                st.error("🚫 The video is unavailable (removed, private, or restricted).")
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")

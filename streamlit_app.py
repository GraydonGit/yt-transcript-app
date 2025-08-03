import streamlit as st
import nltk
import time
import random
import requests
import json
import re
from urllib.parse import urlparse, parse_qs, quote
from bs4 import BeautifulSoup

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from yt_dlp import YoutubeDL
from rake_nltk import Rake

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

# 🌐 HTML scraping method to extract transcript from YouTube page
def extract_transcript_from_html(video_id):
    """Extract transcript by scraping YouTube page HTML directly"""
    try:
        # Construct YouTube URL
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Set headers to mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        # Make request to YouTube page with timeout
        response = requests.get(youtube_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        
        html_content = response.text
        
        # Look for transcript data in the HTML content using regex
        transcript_text = None
        
        # Method 1: Look for captionTracks in the HTML
        caption_tracks_pattern = r'"captionTracks":\s*(\[.*?\])'
        caption_match = re.search(caption_tracks_pattern, html_content, re.DOTALL)
        
        if caption_match:
            try:
                caption_tracks_str = caption_match.group(1)
                # Fix common JSON issues
                caption_tracks_str = re.sub(r'\\"', '"', caption_tracks_str)
                caption_tracks = json.loads(caption_tracks_str)
                
                # Find English caption track
                for track in caption_tracks:
                    lang_code = track.get('languageCode', '')
                    if lang_code.startswith('en') or lang_code == 'a.en':
                        caption_url = track.get('baseUrl')
                        if caption_url:
                            # Fetch the caption file
                            try:
                                caption_response = requests.get(caption_url, headers=headers, timeout=10)
                                if caption_response.status_code == 200:
                                    # Parse XML captions
                                    caption_content = caption_response.text
                                    
                                    # Extract text from XML using regex (more reliable than BeautifulSoup for this)
                                    text_pattern = r'<text[^>]*>([^<]+)</text>'
                                    text_matches = re.findall(text_pattern, caption_content)
                                    
                                    if text_matches:
                                        # Clean and join the text
                                        transcript_parts = []
                                        for text in text_matches:
                                            # Decode HTML entities and clean
                                            clean_text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
                                            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                                            if clean_text:
                                                transcript_parts.append(clean_text)
                                        
                                        if transcript_parts:
                                            transcript_text = ' '.join(transcript_parts)
                                            break
                            except Exception as e:
                                continue
            except Exception as e:
                pass
        
        # Method 2: Look for ytInitialPlayerResponse
        if not transcript_text:
            player_response_pattern = r'var ytInitialPlayerResponse\s*=\s*({.*?});'
            player_match = re.search(player_response_pattern, html_content, re.DOTALL)
            
            if player_match:
                try:
                    player_response_str = player_match.group(1)
                    player_response = json.loads(player_response_str)
                    
                    # Navigate to captions
                    captions = player_response.get('captions', {})
                    caption_tracks = captions.get('playerCaptionsTracklistRenderer', {}).get('captionTracks', [])
                    
                    for track in caption_tracks:
                        lang_code = track.get('languageCode', '')
                        if lang_code.startswith('en') or lang_code == 'a.en':
                            caption_url = track.get('baseUrl')
                            if caption_url:
                                try:
                                    caption_response = requests.get(caption_url, headers=headers, timeout=10)
                                    if caption_response.status_code == 200:
                                        caption_content = caption_response.text
                                        text_pattern = r'<text[^>]*>([^<]+)</text>'
                                        text_matches = re.findall(text_pattern, caption_content)
                                        
                                        if text_matches:
                                            transcript_parts = []
                                            for text in text_matches:
                                                clean_text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
                                                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                                                if clean_text:
                                                    transcript_parts.append(clean_text)
                                            
                                            if transcript_parts:
                                                transcript_text = ' '.join(transcript_parts)
                                                break
                                except Exception as e:
                                    continue
                except Exception as e:
                    pass
        
        if transcript_text and len(transcript_text.strip()) > 10:
            return f"🌐 Extracted from HTML: {transcript_text[:2000]}{'...' if len(transcript_text) > 2000 else ''}"
        else:
            return None
            
    except Exception as e:
        return None

# 🔄 Alternative transcript extraction methods
def extract_transcript_alternative(video_id):
    """Try alternative methods to extract transcript when standard API fails"""
    
    # Method 1: Try with delays and different approaches
    alternative_approaches = [
        # Try with different language combinations
        lambda vid: YouTubeTranscriptApi.get_transcript(vid, languages=['en-US', 'en', 'en-GB']),
        lambda vid: YouTubeTranscriptApi.get_transcript(vid, languages=['en']),
        lambda vid: YouTubeTranscriptApi.get_transcript(vid, languages=['en-US']),
        # Try without specifying languages
        lambda vid: YouTubeTranscriptApi.get_transcript(vid),
    ]
    
    for i, approach in enumerate(alternative_approaches):
        try:
            # Add progressive delays
            if i > 0:
                time.sleep(random.uniform(2, 5))
            
            # Try the approach
            transcript = approach(video_id)
            
            if transcript:
                formatter = TextFormatter()
                return formatter.format_transcript(transcript)
                
        except Exception as e:
            continue
    
    # Method 2: Try using list_transcripts with more patience
    try:
        time.sleep(random.uniform(3, 6))
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to get any available transcript
        for transcript in transcript_list:
            try:
                transcript_data = transcript.fetch()
                formatter = TextFormatter()
                return f"✅ Found transcript in {transcript.language}:\n\n" + formatter.format_transcript(transcript_data)
            except:
                continue
                
    except Exception as e:
        pass
    
    return None

# 📜 Get transcript (if available)
def extract_transcript(video_id):
    try:
        # Try multiple approaches to get transcript
        
        # Approach 1: Try default (usually auto-generated English)
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            formatter = TextFormatter()
            return formatter.format_transcript(transcript)
        except Exception as e1:
            pass
        
        # Approach 2: Try with specific language codes
        for lang_codes in [['en'], ['en-US'], ['en-GB'], ['en-CA'], ['en-AU']]:
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=lang_codes)
                formatter = TextFormatter()
                return formatter.format_transcript(transcript)
            except Exception as e2:
                continue
        
        # Approach 3: Try to list available transcripts and use any English one
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try to find any English transcript (manual or auto-generated)
            for transcript in transcript_list:
                if transcript.language_code.startswith('en'):
                    transcript_data = transcript.fetch()
                    formatter = TextFormatter()
                    return formatter.format_transcript(transcript_data)
            
            # If no English, try the first available transcript
            for transcript in transcript_list:
                transcript_data = transcript.fetch()
                formatter = TextFormatter()
                return f"⚠️ Using {transcript.language} transcript:\n\n" + formatter.format_transcript(transcript_data)
                
        except Exception as e3:
            pass
        
        # Try alternative methods before giving up
        st.info("🔄 Trying alternative extraction methods...")
        alternative_result = extract_transcript_alternative(video_id)
        if alternative_result:
            return alternative_result
        
        # Try HTML scraping as final attempt
        st.info("🌐 Trying HTML scraping method...")
        html_result = extract_transcript_from_html(video_id)
        if html_result:
            return html_result
        
        # If all approaches fail, return helpful error
        return f"🚨 Could not retrieve transcript for video ID: {video_id}. This may be due to:\n" + \
               "• YouTube API access restrictions (403 Forbidden)\n" + \
               "• Geographic/IP blocking on Streamlit Cloud\n" + \
               "• Rate limiting or policy changes\n" + \
               "• Video has restricted transcript access"
            
    except Exception as e:
        error_msg = str(e).lower()
        
        # Handle specific error cases
        if "403" in error_msg or "forbidden" in error_msg:
            return "🚨 Access Forbidden (403): YouTube is blocking transcript access from this server. This is likely due to Streamlit Cloud IP restrictions or rate limiting."
        elif "no element found" in error_msg or "line 1, column 0" in error_msg:
            return "🚨 No transcript available for this video. The video may not have captions enabled or may be restricted."
        elif "could not retrieve a transcript" in error_msg:
            return "🚨 Transcript not available. This video may not have captions or may be private/restricted."
        elif "video is unavailable" in error_msg:
            return "🚨 Video is unavailable or private. Please try a different video."
        elif "transcript disabled" in error_msg:
            return "🚨 Transcripts are disabled for this video."
        else:
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

# Add notice about potential limitations
st.info("📋 **Note**: Due to YouTube's access restrictions, transcript extraction may be limited on cloud platforms. For best results, run this app locally.")

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
        
        # Check if transcript extraction failed due to restrictions
        if transcript.startswith("🚨"):
            st.error(transcript)
            
            # Offer manual input as fallback
            st.subheader("📝 Manual Transcript Input (Fallback)")
            st.info("💡 **Workaround**: You can manually copy-paste the transcript from YouTube and analyze it here.")
            
            manual_transcript = st.text_area(
                "Paste transcript text here:",
                placeholder="Copy the transcript from YouTube and paste it here to extract keywords...",
                height=200
            )
            
            if manual_transcript.strip():
                st.subheader("🧠 Top Keywords (from manual input)")
                manual_keywords = extract_keywords(manual_transcript)
                if manual_keywords:
                    st.write(", ".join(manual_keywords))
                else:
                    st.info("No keywords found in the provided text.")
                    
                st.subheader("📝 Processed Transcript")
                st.text_area("Your transcript:", manual_transcript, height=300)
        else:
            # Normal flow when transcript extraction works
            keywords = extract_keywords(transcript)
            if keywords:
                st.write(", ".join(keywords))
            else:
                st.info("No keywords found in this transcript.")

            st.subheader("📝 Transcript")
            st.text_area("Copyable Transcript", transcript, height=400)

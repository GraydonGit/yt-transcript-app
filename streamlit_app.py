import streamlit as st
import nltk
import time
import random
import requests
import json
import re
import sys
import locale
import os
from urllib.parse import urlparse, parse_qs, quote
from bs4 import BeautifulSoup

# Set environment variables to force UTF-8 encoding
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.platform.startswith('win'):
    # Force UTF-8 on Windows
    sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
    sys.stderr.reconfigure(encoding='utf-8', errors='ignore')

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from yt_dlp import YoutubeDL
from rake_nltk import Rake

# Import Playwright for browser automation
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright not available - browser automation disabled")

# Set UTF-8 encoding for better Unicode handling
try:
    if sys.platform.startswith('win'):
        # For Windows, ensure we can handle Unicode
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
except:
    pass

# Helper function to safely handle text encoding - BULLETPROOF VERSION
def safe_text_encode(text):
    """Aggressively safe text encoding to prevent all Unicode errors"""
    if not text:
        return ""
    
    try:
        # Convert to string if not already
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='replace')
        
        text = str(text)
        
        # Replace problematic Unicode characters that cause charmap errors
        # This specifically targets the \u0101 character and similar ones
        problematic_chars = {
            '\u0101': 'a',  # ā -> a
            '\u0113': 'e',  # ē -> e
            '\u012b': 'i',  # ī -> i
            '\u014d': 'o',  # ō -> o
            '\u016b': 'u',  # ū -> u
            '\u0100': 'A',  # Ā -> A
            '\u0112': 'E',  # Ē -> E
            '\u012a': 'I',  # Ī -> I
            '\u014c': 'O',  # Ō -> O
            '\u016a': 'U',  # Ū -> U
        }
        
        # Replace known problematic characters
        for unicode_char, replacement in problematic_chars.items():
            text = text.replace(unicode_char, replacement)
        
        # Remove any character that can't be encoded in ASCII (most aggressive approach)
        clean_text = ''.join(char for char in text if ord(char) < 128)
        
        # If the text is now empty or too short, provide a fallback
        if not clean_text or len(clean_text.strip()) < 3:
            return "[Text contains special characters that cannot be displayed]"
        
        return clean_text
        
    except Exception as e:
        # Ultimate fallback - return a safe message
        return "[Error processing text - contains unsupported characters]"

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
            # Handle Unicode encoding issues
            clean_transcript = safe_text_encode(transcript_text)
            return f"🌐 Extracted from HTML: {clean_transcript[:2000]}{'...' if len(clean_transcript) > 2000 else ''}"
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
                transcript_text = formatter.format_transcript(transcript)
                # Handle Unicode encoding issues
                return safe_text_encode(transcript_text)
                
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
                transcript_text = formatter.format_transcript(transcript_data)
                # Handle Unicode encoding issues
                clean_text = safe_text_encode(transcript_text)
                return f"✅ Found transcript in {safe_text_encode(transcript.language)}:\n\n" + clean_text
            except Exception as e:
                print(f"Failed to fetch transcript in {transcript.language}: {e}")
                continue
                
    except Exception as e:
        pass
    
    return None

# 🔄 Enhanced transcript extraction (multiple approaches)
def extract_transcript_with_enhanced_methods(video_id):
    """Enhanced transcript extraction using multiple reliable methods"""
    
    debug_msg = f"🔄 DEBUG: Starting enhanced extraction for video_id: {video_id}"
    print(debug_msg)
    # Also show in Streamlit UI for debugging
    try:
        import streamlit as st
        st.write(debug_msg)
    except:
        pass
    
    # Method 1: Comprehensive YouTube transcript API with extensive language support
    try:
        debug_msg = "🔄 DEBUG: Starting comprehensive transcript API extraction..."
        print(debug_msg)
        try:
            import streamlit as st
            st.write(debug_msg)
        except:
            pass
            
        # First, try to get the list of available transcripts
        try:
            debug_msg = "🔄 DEBUG: Getting available transcript list..."
            print(debug_msg)
            try:
                import streamlit as st
                st.write(debug_msg)
            except:
                pass
                
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available_languages = []
            
            for transcript in transcript_list:
                available_languages.append({
                    'language_code': transcript.language_code,
                    'language': transcript.language,
                    'is_generated': transcript.is_generated,
                    'is_translatable': transcript.is_translatable
                })
            
            debug_msg = f"🔄 DEBUG: Found {len(available_languages)} available transcripts"
            print(debug_msg)
            try:
                import streamlit as st
                st.write(debug_msg)
                # Show available languages in UI
                for lang in available_languages[:5]:  # Show first 5
                    st.write(f"  - {lang['language_code']} ({lang['language']}) - Generated: {lang['is_generated']}")
            except:
                pass
                
        except Exception as list_error:
            debug_msg = f"❌ DEBUG: Could not get transcript list: {safe_text_encode(str(list_error))}"
            print(debug_msg)
            try:
                import streamlit as st
                st.write(debug_msg)
            except:
                pass
            available_languages = []
        
        # Try comprehensive language attempts
        language_attempts = [
            # English variants
            ['en'],
            ['en-US'], 
            ['en-GB'],
            ['en-CA'],
            ['en-AU'],
            ['en-IN'],
            ['en-ZA'],
            # Auto-generated English
            ['a.en'],
            # Other common languages
            ['es', 'en'],  # Spanish with English fallback
            ['fr', 'en'],  # French with English fallback
            ['de', 'en'],  # German with English fallback
            ['it', 'en'],  # Italian with English fallback
            ['pt', 'en'],  # Portuguese with English fallback
            ['ja', 'en'],  # Japanese with English fallback
            ['ko', 'en'],  # Korean with English fallback
            ['zh', 'en'],  # Chinese with English fallback
            ['hi', 'en'],  # Hindi with English fallback
            ['ar', 'en'],  # Arabic with English fallback
            ['ru', 'en'],  # Russian with English fallback
            None  # Let API choose automatically
        ]
        
        # If we have available languages, prioritize them
        if available_languages:
            # Add available English variants to the front
            priority_attempts = []
            for lang_info in available_languages:
                if 'en' in lang_info['language_code'].lower():
                    priority_attempts.append([lang_info['language_code']])
            
            # Add other available languages
            for lang_info in available_languages:
                if 'en' not in lang_info['language_code'].lower():
                    priority_attempts.append([lang_info['language_code']])
            
            # Combine with original attempts
            language_attempts = priority_attempts + language_attempts
        
        for i, languages in enumerate(language_attempts):
            try:
                debug_msg = f"🔄 DEBUG: Attempt {i+1}/{len(language_attempts)}: {languages}"
                print(debug_msg)
                try:
                    import streamlit as st
                    st.write(debug_msg)
                except:
                    pass
                    
                if languages:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
                else:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id)
                    
                # Validate transcript content
                if not transcript or len(transcript) == 0:
                    debug_msg = f"❌ DEBUG: Empty transcript returned for {languages}"
                    print(debug_msg)
                    try:
                        import streamlit as st
                        st.write(debug_msg)
                    except:
                        pass
                    continue
                    
                formatter = TextFormatter()
                transcript_text = formatter.format_transcript(transcript)
                
                # Validate transcript text
                if not transcript_text or len(transcript_text.strip()) < 10:
                    debug_msg = f"❌ DEBUG: Transcript too short or empty for {languages}"
                    print(debug_msg)
                    try:
                        import streamlit as st
                        st.write(debug_msg)
                    except:
                        pass
                    continue
                
                clean_transcript = safe_text_encode(transcript_text)
                
                success_msg = f"✅ SUCCESS: Transcript extracted! Language: {languages}, Length: {len(clean_transcript)} chars"
                print(success_msg)
                try:
                    import streamlit as st
                    st.write(success_msg)
                    st.write(f"Preview: {clean_transcript[:200]}...")
                except:
                    pass
                    
                return f"✅ Direct API ({languages}): {clean_transcript}"
                
            except Exception as lang_error:
                error_msg = f"❌ DEBUG: Attempt {i+1} failed: {safe_text_encode(str(lang_error))}"
                print(error_msg)
                try:
                    import streamlit as st
                    st.write(error_msg)
                except:
                    pass
                continue
                
    except Exception as api_error:
        error_msg = f"❌ DEBUG: Comprehensive API method failed: {safe_text_encode(str(api_error))}"
        print(error_msg)
        try:
            import streamlit as st
            st.write(error_msg)
        except:
            pass
    
    # Method 2: Try transcript list approach
    try:
        debug_msg = "🔄 DEBUG: Trying transcript list approach..."
        print(debug_msg)
        try:
            import streamlit as st
            st.write(debug_msg)
        except:
            pass
            
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to find English transcripts first
        for transcript in transcript_list:
            try:
                if 'en' in transcript.language_code.lower():
                    debug_msg = f"🔄 DEBUG: Found English transcript: {transcript.language_code}"
                    print(debug_msg)
                    try:
                        import streamlit as st
                        st.write(debug_msg)
                    except:
                        pass
                        
                    transcript_data = transcript.fetch()
                    formatter = TextFormatter()
                    transcript_text = formatter.format_transcript(transcript_data)
                    clean_transcript = safe_text_encode(transcript_text)
                    
                    success_msg = f"✅ SUCCESS: Transcript list extraction successful ({transcript.language_code})"
                    print(success_msg)
                    try:
                        import streamlit as st
                        st.write(success_msg)
                    except:
                        pass
                        
                    return f"✅ Transcript List ({transcript.language_code}): {clean_transcript}"
            except Exception as transcript_error:
                continue
                
        # If no English, try any available transcript
        for transcript in transcript_list:
            try:
                debug_msg = f"🔄 DEBUG: Trying transcript: {transcript.language_code}"
                print(debug_msg)
                try:
                    import streamlit as st
                    st.write(debug_msg)
                except:
                    pass
                    
                transcript_data = transcript.fetch()
                formatter = TextFormatter()
                transcript_text = formatter.format_transcript(transcript_data)
                clean_transcript = safe_text_encode(transcript_text)
                
                success_msg = f"✅ SUCCESS: Alternative language extraction successful ({transcript.language_code})"
                print(success_msg)
                try:
                    import streamlit as st
                    st.write(success_msg)
                except:
                    pass
                    
                return f"✅ Alternative Language ({transcript.language_code}): {clean_transcript}"
            except Exception as transcript_error:
                continue
                
    except Exception as list_error:
        error_msg = f"❌ DEBUG: Transcript list method failed: {safe_text_encode(str(list_error))}"
        print(error_msg)
        try:
            import streamlit as st
            st.write(error_msg)
        except:
            pass
    
    # Method 3: Enhanced HTTP scraping approach
    try:
        debug_msg = "🔄 DEBUG: Trying enhanced HTTP scraping..."
        print(debug_msg)
        try:
            import streamlit as st
            st.write(debug_msg)
        except:
            pass
            
        # Use requests with better headers to mimic real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(youtube_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            # Look for transcript data in the page source
            page_content = response.text
            
            # Try to find transcript data patterns
            transcript_patterns = [
                r'"captions".*?"playerCaptionsTracklistRenderer".*?"captionTracks":\[(.*?)\]',
                r'"transcriptRenderer".*?"content".*?"runs":\[(.*?)\]',
                r'"timedTextTrack".*?"baseUrl":"(.*?)"'
            ]
            
            for pattern in transcript_patterns:
                matches = re.search(pattern, page_content, re.DOTALL)
                if matches:
                    debug_msg = f"✅ DEBUG: Found transcript pattern in page source"
                    print(debug_msg)
                    try:
                        import streamlit as st
                        st.write(debug_msg)
                    except:
                        pass
                    
                    # Try to extract actual transcript content
                    try:
                        # Look for common transcript text patterns in the page
                        text_patterns = [
                            r'"text":"([^"]+)"',
                            r'"runs":\[\{"text":"([^"]+)"',
                            r'<text[^>]*>([^<]+)</text>',
                            r'"caption":"([^"]+)"',
                            r'"content":"([^"]+)"'
                        ]
                        
                        extracted_texts = []
                        for text_pattern in text_patterns:
                            text_matches = re.findall(text_pattern, page_content)
                            if text_matches:
                                # Filter out short/meaningless matches
                                meaningful_texts = [text for text in text_matches if len(text) > 10 and not text.startswith('http')]
                                if meaningful_texts:
                                    extracted_texts.extend(meaningful_texts[:20])  # Limit to first 20 matches
                                    break
                        
                        if extracted_texts:
                            # Combine and clean the extracted text
                            combined_text = ' '.join(extracted_texts)
                            # Decode common HTML entities
                            combined_text = combined_text.replace('\\n', ' ').replace('\\t', ' ')
                            combined_text = combined_text.replace('\u0026', '&').replace('\u003c', '<').replace('\u003e', '>')
                            
                            clean_transcript = safe_text_encode(combined_text)
                            
                            if len(clean_transcript.strip()) > 50:  # Ensure we have meaningful content
                                success_msg = f"✅ SUCCESS: HTTP scraping extracted transcript! Length: {len(clean_transcript)} chars"
                                print(success_msg)
                                try:
                                    import streamlit as st
                                    st.write(success_msg)
                                    st.write(f"Preview: {clean_transcript[:200]}...")
                                except:
                                    pass
                                    
                                return f"✅ HTTP Scraping: {clean_transcript}"
                            else:
                                debug_msg = f"❌ DEBUG: Extracted text too short: {len(clean_transcript)} chars"
                                print(debug_msg)
                                try:
                                    import streamlit as st
                                    st.write(debug_msg)
                                except:
                                    pass
                        else:
                            debug_msg = f"❌ DEBUG: No meaningful text extracted from patterns"
                            print(debug_msg)
                            try:
                                import streamlit as st
                                st.write(debug_msg)
                            except:
                                pass
                                
                    except Exception as extract_error:
                        error_msg = f"❌ DEBUG: Text extraction failed: {safe_text_encode(str(extract_error))}"
                        print(error_msg)
                        try:
                            import streamlit as st
                            st.write(error_msg)
                        except:
                            pass
                    
    except Exception as scraping_error:
        error_msg = f"❌ DEBUG: HTTP scraping failed: {safe_text_encode(str(scraping_error))}"
        print(error_msg)
        try:
            import streamlit as st
            st.write(error_msg)
        except:
            pass
            debug_msg = "🎭 DEBUG: Launching Chromium browser..."
            print(debug_msg)
            try:
                import streamlit as st
                st.write(debug_msg)
            except:
                pass
                
            try:
                # Try multiple browser launch strategies
                browser = None
                launch_strategies = [
                    # Strategy 1: Standard headless with Windows-friendly options
                    {
                        'headless': True,
                        'timeout': 30000,
                        'args': [
                            '--no-sandbox',
                            '--disable-dev-shm-usage',
                            '--disable-blink-features=AutomationControlled',
                            '--disable-extensions',
                            '--disable-gpu',
                            '--disable-web-security',
                            '--allow-running-insecure-content',
                            '--disable-features=VizDisplayCompositor'
                        ]
                    },
                    # Strategy 2: Try Firefox as fallback
                    {'browser_type': 'firefox', 'headless': True, 'timeout': 30000},
                    # Strategy 3: Try WebKit as fallback
                    {'browser_type': 'webkit', 'headless': True, 'timeout': 30000},
                    # Strategy 4: Non-headless mode (visible browser)
                    {
                        'headless': False,
                        'timeout': 30000,
                        'args': ['--no-sandbox', '--disable-dev-shm-usage']
                    }
                ]
                
                for i, strategy in enumerate(launch_strategies):
                    try:
                        debug_msg = f"🎭 DEBUG: Trying launch strategy {i+1}/{len(launch_strategies)}..."
                        print(debug_msg)
                        try:
                            import streamlit as st
                            st.write(debug_msg)
                        except:
                            pass
                            
                        browser_type = strategy.pop('browser_type', 'chromium')
                        if browser_type == 'firefox':
                            browser = p.firefox.launch(**strategy)
                        elif browser_type == 'webkit':
                            browser = p.webkit.launch(**strategy)
                        else:
                            browser = p.chromium.launch(**strategy)
                            
                        debug_msg = f"🎭 DEBUG: {browser_type.title()} browser launched successfully!"
                        print(debug_msg)
                        try:
                            import streamlit as st
                            st.write(debug_msg)
                        except:
                            pass
                        break
                        
                    except Exception as strategy_error:
                        error_msg = f"🚨 DEBUG: Strategy {i+1} failed: {safe_text_encode(str(strategy_error))}"
                        print(error_msg)
                        try:
                            import streamlit as st
                            st.write(error_msg)
                        except:
                            pass
                        continue
                
                if not browser:
                    error_msg = "🚨 DEBUG: All browser launch strategies failed"
                    print(error_msg)
                    try:
                        import streamlit as st
                        st.write(error_msg)
                    except:
                        pass
                    return error_msg
                    
            except Exception as browser_error:
                error_msg = f"🚨 DEBUG: Browser launch failed: {safe_text_encode(str(browser_error))}"
                print(error_msg)
                try:
                    import streamlit as st
                    st.write(error_msg)
                except:
                    pass
                return error_msg
                
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                debug_msg = "🎭 DEBUG: Browser context created"
                print(debug_msg)
                try:
                    import streamlit as st
                    st.write(debug_msg)
                except:
                    pass
                    
            except Exception as context_error:
                error_msg = f"🚨 DEBUG: Context creation failed: {safe_text_encode(str(context_error))}"
                print(error_msg)
                try:
                    import streamlit as st
                    st.write(error_msg)
                except:
                    pass
                browser.close()
                return error_msg
                
            try:
                page = context.new_page()
                debug_msg = "🎭 DEBUG: New page created"
                print(debug_msg)
                try:
                    import streamlit as st
                    st.write(debug_msg)
                except:
                    pass
                    
            except Exception as page_error:
                error_msg = f"🚨 DEBUG: Page creation failed: {safe_text_encode(str(page_error))}"
                print(error_msg)
                try:
                    import streamlit as st
                    st.write(error_msg)
                except:
                    pass
                browser.close()
                return error_msg
            
            # Navigate to YouTube video
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            print(f"🎭 DEBUG: Navigating to: {youtube_url}")
            
            try:
                page.goto(youtube_url, wait_until='networkidle', timeout=30000)
                print("🎭 DEBUG: Page loaded successfully")
            except Exception as nav_error:
                print(f"🚨 DEBUG: Navigation failed: {nav_error}")
                browser.close()
                return f"🚨 Navigation failed: {safe_text_encode(str(nav_error))}"
            
            # Wait for page to load
            print("🎭 DEBUG: Waiting for page to fully load...")
            page.wait_for_timeout(5000)
            
            # Try to find and click the transcript button
            transcript_text = None
            
            try:
                print("🎭 DEBUG: Looking for transcript button...")
                # Look for the "Show transcript" button - multiple possible selectors
                transcript_selectors = [
                    'button[aria-label*="transcript"]',
                    'button[aria-label*="Transcript"]',
                    'button[title*="transcript"]',
                    'button[title*="Transcript"]',
                    '[data-testid="transcript-button"]',
                    'yt-button-renderer:has-text("Show transcript")',
                    'button:has-text("Show transcript")',
                    'button:has-text("Transcript")'
                ]
                
                transcript_button = None
                for i, selector in enumerate(transcript_selectors):
                    try:
                        print(f"🎭 DEBUG: Trying selector {i+1}/{len(transcript_selectors)}: {selector}")
                        transcript_button = page.wait_for_selector(selector, timeout=2000)
                        if transcript_button:
                            print(f"✅ DEBUG: Found transcript button with selector: {selector}")
                            break
                    except Exception as sel_error:
                        print(f"❌ DEBUG: Selector {selector} failed: {sel_error}")
                        continue
                
                if not transcript_button:
                    print("🚨 DEBUG: No transcript button found with any selector")
                
                if transcript_button:
                    print("🎭 DEBUG: Clicking transcript button...")
                    # Click the transcript button
                    transcript_button.click()
                    page.wait_for_timeout(3000)
                    print("🎭 DEBUG: Waiting for transcript panel to load...")
                    
                    # Try to extract transcript text from various possible containers
                    transcript_containers = [
                        '[data-testid="transcript-segment"]',
                        '.ytd-transcript-segment-renderer',
                        '.segment-text',
                        '#transcript-scrollbox',
                        '.transcript-text',
                        '[role="button"] .segment-text'
                    ]
                    
                    for i, container_selector in enumerate(transcript_containers):
                        try:
                            print(f"🎭 DEBUG: Trying transcript container {i+1}/{len(transcript_containers)}: {container_selector}")
                            elements = page.query_selector_all(container_selector)
                            print(f"🎭 DEBUG: Found {len(elements)} elements with selector {container_selector}")
                            
                            if elements:
                                transcript_parts = []
                                for j, element in enumerate(elements[:10]):  # Limit to first 10 for debugging
                                    text = element.inner_text().strip()
                                    if text:
                                        transcript_parts.append(text)
                                        print(f"🎭 DEBUG: Element {j+1} text: {text[:50]}...")
                                
                                if transcript_parts:
                                    transcript_text = ' '.join(transcript_parts)
                                    print(f"✅ DEBUG: Extracted transcript using selector: {container_selector}")
                                    print(f"🎭 DEBUG: Transcript length: {len(transcript_text)} characters")
                                    break
                        except Exception as e:
                            print(f"❌ DEBUG: Error with selector {container_selector}: {e}")
                            continue
                
                # If transcript button method didn't work, try alternative approaches
                if not transcript_text:
                    # Try to extract from video description or comments
                    print("Transcript button method failed, trying alternative extraction...")
                    
                    # Look for transcript in video description
                    description_selectors = [
                        '#description-text',
                        '.ytd-video-secondary-info-renderer #description',
                        '#meta-contents #description'
                    ]
                    
                    for desc_selector in description_selectors:
                        try:
                            desc_element = page.query_selector(desc_selector)
                            if desc_element:
                                desc_text = desc_element.inner_text()
                                if len(desc_text) > 500:  # Likely contains transcript
                                    transcript_text = desc_text
                                    print("Extracted transcript from video description")
                                    break
                        except:
                            continue
                            
            except Exception as e:
                print(f"Error during transcript extraction: {e}")
            
            finally:
                browser.close()
            
            if transcript_text and len(transcript_text.strip()) > 50:
                # Clean and encode the transcript text
                clean_transcript = safe_text_encode(transcript_text)
                return f"🎭 Extracted via browser automation: {clean_transcript}"
            else:
                return "🚨 Could not extract transcript via browser automation - transcript may not be available or video may be restricted"
                
    except Exception as e:
        error_msg = safe_text_encode(str(e))
        return f"🚨 Browser automation failed: {error_msg}"

# System-level encoding protection wrapper
def safe_transcript_operation(operation_func, *args, **kwargs):
    """Wrap any transcript operation to catch encoding errors at system level"""
    try:
        # Set locale to handle Unicode properly
        if sys.platform.startswith('win'):
            try:
                locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            except:
                try:
                    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
                except:
                    pass
        
        result = operation_func(*args, **kwargs)
        return result
    except UnicodeEncodeError as e:
        print(f"Unicode encoding error caught: {e}")
        return "[Transcript contains characters that cannot be displayed - encoding error prevented]"
    except Exception as e:
        error_str = str(e)
        if 'charmap' in error_str or 'codec' in error_str or 'encode' in error_str:
            print(f"Encoding-related error caught: {e}")
            return "[Transcript extraction failed due to character encoding issues]"
        raise e

# 📜 Get transcript with Playwright as primary method
def extract_transcript(video_id):
    """Extract transcript from YouTube video with multiple fallback approaches"""
    def _extract_transcript_internal(video_id):
        print(f"🔍 DEBUG: Starting transcript extraction for video_id: {video_id}")
        print(f"🔍 DEBUG: PLAYWRIGHT_AVAILABLE = {PLAYWRIGHT_AVAILABLE}")
        
        # Method 1: 🔄 Enhanced transcript extraction (PRIMARY METHOD)
        try:
            print("🔄 DEBUG: Trying enhanced transcript extraction...")
            enhanced_result = extract_transcript_with_enhanced_methods(video_id)
            print(f"🔄 DEBUG: Enhanced result: {enhanced_result[:100] if enhanced_result else 'None'}...")
            if enhanced_result and not enhanced_result.startswith("🚨"):
                print("✅ DEBUG: Enhanced extraction succeeded, returning result")
                return enhanced_result
            else:
                print(f"❌ DEBUG: Enhanced extraction failed or returned error: {enhanced_result}")
        except Exception as e:
            print(f"❌ DEBUG: Enhanced extraction method exception: {e}")
        
        # Method 2: Default API approach
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            formatter = TextFormatter()
            transcript_text = formatter.format_transcript(transcript)
            return f"✅ Default API: {transcript_text}"
        except Exception as e:
            print(f"Method 2 failed: {e}")
        
        try:
            # Method 3: Try with language specification
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US'])
            formatter = TextFormatter()
            transcript_text = formatter.format_transcript(transcript)
            return f"✅ Language-specific API: {transcript_text}"
        except Exception as e:
            print(f"Method 3 failed: {e}")
        
        try:
            # Method 4: List available transcripts and try the first one
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try to get English transcript first
            try:
                transcript = transcript_list.find_transcript(['en', 'en-US'])
                transcript_data = transcript.fetch()
                formatter = TextFormatter()
                transcript_text = formatter.format_transcript(transcript_data)
                return f"✅ English transcript found: {transcript_text}"
            except:
                # If no English, try the first available
                for transcript in transcript_list:
                    try:
                        transcript_data = transcript.fetch()
                        formatter = TextFormatter()
                        transcript_text = formatter.format_transcript(transcript_data)
                        return f"✅ Available transcript ({transcript.language}): {transcript_text}"
                    except:
                        continue
        except Exception as e:
            print(f"Method 4 failed: {e}")
        
        try:
            # Method 5: HTML scraping fallback
            transcript_text = scrape_transcript_from_html(video_id)
            if transcript_text:
                return f"✅ HTML scraping: {transcript_text}"
        except Exception as e:
            print(f"Method 5 failed: {e}")
        
        try:
            # Method 6: Alternative extraction approach
            transcript_text = alternative_transcript_extraction(video_id)
            if transcript_text:
                return f"✅ Alternative method: {transcript_text}"
        except Exception as e:
            print(f"Method 6 failed: {e}")
        
        return "❌ All transcript extraction methods failed. This could be due to:"+ \
               "\n• Video has no transcript available"+ \
               "\n• Geographic restrictions or API blocking"+ \
               "\n• Rate limiting or temporary access issues"+ \
               "\n\n💡 Try using the manual transcript input below."
    
    return safe_transcript_operation(_extract_transcript_internal, video_id)
        
# 🧠 Extract keywords
def extract_keywords(text, num=10):
    try:
        ensure_nltk_ready()
        # Clean the text to handle Unicode encoding issues
        clean_text = safe_text_encode(text)
        if not clean_text or len(clean_text.strip()) < 10:
            return []
        
        rake = Rake()
        rake.extract_keywords_from_text(clean_text)
        keywords = rake.get_ranked_phrases()[:num]
        
        # Clean each keyword to handle any remaining encoding issues
        clean_keywords = []
        for keyword in keywords:
            clean_keyword = safe_text_encode(str(keyword))
            if clean_keyword and len(clean_keyword.strip()) > 0:
                clean_keywords.append(clean_keyword)
        
        return clean_keywords
    except Exception as e:
        print(f"Error in keyword extraction: {e}")
        return []

# 📊 Get metadata with yt-dlp
def get_metadata(url):
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'nocheckcertificate': True
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Clean all text fields to handle Unicode encoding issues
            title = safe_text_encode(info.get("title", "")) if info.get("title") else "No title available"
            description = info.get("description", "")
            if description:
                clean_description = safe_text_encode(description)[:300] + "..." if len(description) > 300 else safe_text_encode(description)
            else:
                clean_description = "No description available"
            
            return {
                "Title": title,
                "Views": info.get("view_count"),
                "Length (sec)": info.get("duration"),
                "Publish Date": info.get("upload_date"),
                "Description": clean_description
            }
    except Exception as e:
        print(f"Error extracting metadata: {e}")
        return {
            "Title": "Error extracting title",
            "Views": "N/A",
            "Length (sec)": "N/A",
            "Publish Date": "N/A",
            "Description": "Error extracting description"
        }

# 🎨 Clean UI styling
st.set_page_config(page_title="YouTube Transcript + SEO Tool", layout="centered")
st.markdown("""
    <style>
    /* Light, clean styling for better readability */
    .stTextArea textarea {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #ddd;
        border-radius: 4px;
    }
    .stTextInput > div > div > input {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #ddd;
    }
    /* Ensure labels are visible */
    .stTextInput label, .stTextArea label {
        color: #262730;
        font-weight: 500;
    }
    /* Better form styling */
    .stForm {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e9ecef;
    }
    </style>
""", unsafe_allow_html=True)

# 🎛️ App UI
st.title("📺 YouTube Transcript + SEO Info")

# Add notice about potential limitations and instructions
st.warning("⚠️ **Important**: YouTube restricts automated transcript access on cloud platforms like Streamlit Cloud. Use the manual input method below for best results.")

with st.expander("📝 How to get YouTube transcripts manually", expanded=False):
    st.markdown("""
    **Step-by-step instructions:**
    1. Go to your YouTube video
    2. Click the **"..." (More)** button below the video
    3. Click **"Show transcript"**
    4. Copy the transcript text that appears
    5. Paste it in the manual input box below
    
    This method works for any video with captions!
    """)

# Add standalone transcript analyzer
st.subheader("🎯 Quick Transcript Analyzer")
st.info("💡 **Tip**: You can use this section to analyze any transcript text, regardless of the video URL issues above.")

manual_text = st.text_area(
    "Paste any transcript or text here for keyword analysis:",
    placeholder="Paste transcript text here to extract keywords immediately...",
    height=150,
    key="standalone_transcript"
)

if manual_text.strip():
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🧠 Top Keywords")
        standalone_keywords = extract_keywords(manual_text)
        if standalone_keywords:
            st.write(", ".join(standalone_keywords))
        else:
            st.info("No keywords found in the provided text.")
    
    with col2:
        st.subheader("📊 Text Stats")
        word_count = len(manual_text.split())
        char_count = len(manual_text)
        st.metric("Word Count", word_count)
        st.metric("Character Count", char_count)

st.divider()
st.subheader("🔗 Video URL Analysis (Limited on Cloud)")

with st.form("url_form"):
    url = st.text_input("Enter YouTube Video URL")
    submitted = st.form_submit_button("Try Automatic Extraction")

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

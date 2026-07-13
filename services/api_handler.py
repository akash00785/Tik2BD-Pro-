import requests
import logging
from config import key_manager, TIMEOUT
from services.ytdlp_handler import fetch_ytdlp_preview


def _fetch_via_rapidapi(video_url):
    """
    RapidAPI key ব্যবহার করে HD ডাউনলোড লিংক ও ফটো স্লাইডশো ডেটা আনা।
    key না থাকলে বা সব key exhausted হলে success=False রিটার্ন করবে।
    Normal Download এর উপর কোনো প্রভাব নেই।
    """
    api_url = "https://tiktok-video-no-watermark2.p.rapidapi.com/"

    if not key_manager.keys:
        logging.warning("No API keys configured — HD unavailable.")
        return {'success': False, 'error': 'No API keys configured.'}

    for _ in range(len(key_manager.keys)):
        key_obj = key_manager.get_active_key()

        if not key_obj:
            logging.warning("All API keys exhausted — HD unavailable.")
            return {'success': False, 'error': 'Service temporarily unavailable.'}

        headers = {
            "x-rapidapi-host": "tiktok-video-no-watermark2.p.rapidapi.com",
            "x-rapidapi-key": key_obj['val'],
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            response = requests.post(
                api_url,
                headers=headers,
                data={"url": video_url, "hd": "1"},
                timeout=TIMEOUT
            )

            if response.status_code == 429:
                logging.warning("Rate limit hit, rotating key...")
                key_manager.mark_failed(key_obj['val'])
                continue

            if response.status_code != 200:
                logging.error(f"API returned status {response.status_code}")
                continue

            try:
                result = response.json()
            except ValueError:
                logging.error("API returned non-JSON response.")
                continue

            if result.get('code') == 0:
                d = result.get('data', {})

                # Photo/Slideshow mode
                if d.get('images'):
                    return {
                        'success': True,
                        'is_photo': True,
                        'images': d.get('images'),
                        'title': d.get('title') or "TikTok Photos",
                        'author': d.get('author', {}).get('unique_id') or "Unknown"
                    }

                # Standard Video mode
                hd_url = d.get('hdplay') or d.get('play')
                return {
                    'success': True,
                    'is_photo': False,
                    'hd_url': hd_url,
                    'sd_url': d.get('play'),
                    'thumbnail': d.get('cover'),
                    'title': d.get('title') or "Untitled Video",
                    'author': d.get('author', {}).get('unique_id') or "Unknown",
                    'duration': d.get('duration') or 0
                }
            else:
                return {'success': False, 'error': 'Video not found or is private.'}

        except requests.Timeout:
            logging.error(f"Request timed out for URL: {video_url}")
            continue
        except requests.ConnectionError:
            logging.error("Connection error while reaching API.")
            continue
        except Exception as e:
            logging.error(f"Unexpected API Error: {str(e)}")
            continue

    return {'success': False, 'error': 'System busy, please try again.'}


def fetch_tiktok_data(video_url):
    """
    HD এবং Normal উভয়ই RapidAPI থেকে আসে।
    - HD  → hdplay URL (high quality, watermark-free)
    - Normal → play URL (standard quality)
    yt-dlp TikTok bot detection-এ block হয়, তাই সরানো হয়েছে।
    """
    api_result = _fetch_via_rapidapi(video_url)

    if not api_result.get('success'):
        return api_result

    # Photo slideshow
    if api_result.get('is_photo'):
        return api_result

    hd_url  = api_result.get('hd_url')   # hdplay — HD quality CDN URL
    sd_url  = api_result.get('sd_url')   # play   — Normal quality CDN URL
    # hdplay এবং play একই হলে (API limitation) sd হিসেবে play ব্যবহার করা হবে
    hd_available = bool(hd_url)
    sd_available = bool(sd_url)

    if not hd_available and not sd_available:
        return {'success': False, 'error': 'ভিডিও পাওয়া যায়নি।'}

    return {
        'success': True,
        'is_photo': False,
        'hd_available': hd_available,
        'hd_url': hd_url,
        # sd_url হলো RapidAPI-র play CDN URL — সরাসরি browser-এ কাজ করে
        # server proxy দরকার নেই, bandwidth শূন্য
        'sd_available': sd_available,
        'video_url': sd_url,
        'thumbnail': api_result.get('thumbnail'),
        'title': api_result.get('title') or 'Untitled Video',
        'author': api_result.get('author') or 'Unknown',
        'duration': api_result.get('duration') or 0,
    }

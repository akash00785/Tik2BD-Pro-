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
    HD ডাউনলোড RapidAPI key দিয়ে আসে, Normal ডাউনলোড yt-dlp দিয়ে —
    দুইটা একে অপর থেকে সম্পূর্ণ স্বাধীন।
    RapidAPI key না থাকলেও Normal Download কাজ করবে।
    """
    api_result = _fetch_via_rapidapi(video_url)

    # Photo slideshow — সম্পূর্ণ RapidAPI-নির্ভর
    if api_result.get('success') and api_result.get('is_photo'):
        return api_result

    # yt-dlp দিয়ে Normal Download-এর তথ্য আনা
    ytdlp_result = fetch_ytdlp_preview(video_url)

    # দুটোই ফেইল করলে
    if not api_result.get('success') and not ytdlp_result.get('success'):
        return api_result if api_result.get('error') else ytdlp_result

    hd_available = bool(api_result.get('success') and api_result.get('hd_url'))
    sd_available = bool(ytdlp_result.get('success') and ytdlp_result.get('sd_available'))

    if not hd_available and not sd_available:
        return {'success': False, 'error': 'ভিডিও পাওয়া যায়নি বা ডাউনলোড লিংক বের করা যায়নি।'}

    # টাইটেল/থাম্বনেইল: RapidAPI সফল হলে তার থেকে নেওয়া হয়
    source = api_result if api_result.get('success') else ytdlp_result

    return {
        'success': True,
        'is_photo': False,
        'hd_available': hd_available,
        'hd_url': api_result.get('hd_url') if hd_available else None,
        'sd_available': sd_available,
        'video_url': video_url if sd_available else None,
        'thumbnail': source.get('thumbnail'),
        'title': source.get('title') or 'Untitled Video',
        'author': source.get('author') or 'Unknown',
        'duration': source.get('duration') or 0,
    }

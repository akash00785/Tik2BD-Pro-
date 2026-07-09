import requests
import logging
from config import key_manager, TIMEOUT
from services.ytdlp_handler import fetch_ytdlp_preview


def _fetch_via_rapidapi(video_url):
    """
    RapidAPI key ব্যবহার করে HD ডাউনলোড লিংক ও ফটো স্লাইডশো ডেটা আনার
    জন্য মূল ফাংশন। key না থাকলে বা সব key মেয়াদোত্তীর্ণ/exhausted হলে
    success=False রিটার্ন করবে — কিন্তু এতে পুরো রিকোয়েস্ট ফেইল হবে না,
    কারণ Normal ডাউনলোড এখন এর উপর নির্ভর করে না (দেখুন fetch_tiktok_data)।
    """
    api_url = "https://tiktok-video-no-watermark2.p.rapidapi.com/"

    if not key_manager.keys:
        logging.error("Critical: No API keys configured.")
        return {'success': False, 'error': 'Service not configured. Please contact admin.'}

    for _ in range(len(key_manager.keys)):
        key_obj = key_manager.get_active_key()

        if not key_obj:
            logging.error("Critical: All API keys exhausted.")
            return {'success': False, 'error': 'Service temporarily unavailable. Please try later.'}

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

            # FIX: non-200 এরর এখন লগ করা হচ্ছে
            if response.status_code != 200:
                logging.error(f"API returned status {response.status_code} for URL: {video_url}")
                continue

            # FIX: JSON parse আলাদাভাবে handle করা হচ্ছে
            try:
                result = response.json()
            except ValueError:
                logging.error("API returned non-JSON response.")
                continue

            if result.get('code') == 0:
                d = result.get('data', {})

                # Check if it is a Slideshow/Photo mode
                if d.get('images'):
                    return {
                        'success': True,
                        'is_photo': True,
                        'images': d.get('images'),
                        'title': d.get('title') or "TikTok Photos",
                        'author': d.get('author', {}).get('unique_id') or "Unknown"
                    }

                # Standard Video mode
                return {
                    'success': True,
                    'is_photo': False,
                    'hd_url': d.get('hdplay') or d.get('play'),
                    'sd_url': d.get('play'),
                    'thumbnail': d.get('cover'),
                    'title': d.get('title') or "Untitled Video",
                    'author': d.get('author', {}).get('unique_id') or "Unknown",
                    'duration': d.get('duration') or 0
                }
            else:
                return {'success': False, 'error': 'Video/Photo not found or is private.'}

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
    এই দুইটা এখন একে অপরের থেকে স্বাধীন। ফলে RapidAPI-এর সব key মেয়াদ
    ফুরিয়ে গেলে বা exhausted হয়ে গেলেও Normal Download কাজ করবে,
    শুধু HD Download সেই সময়ের জন্য অনুপলব্ধ থাকবে।
    """
    api_result = _fetch_via_rapidapi(video_url)

    # ফটো স্লাইডশো মোড অপরিবর্তিত থাকবে — এখনো সম্পূর্ণভাবে RapidAPI-নির্ভর।
    if api_result.get('success') and api_result.get('is_photo'):
        return api_result

    ytdlp_result = fetch_ytdlp_preview(video_url)

    if not api_result.get('success') and not ytdlp_result.get('success'):
        # দুটোই ফেইল করলে RapidAPI-এর error message-টা দেখানো হয়,
        # কারণ সেটা সাধারণত বেশি নির্দিষ্ট (private/not found ইত্যাদি)।
        return api_result if api_result.get('error') else ytdlp_result

    hd_available = bool(api_result.get('success') and api_result.get('hd_url'))
    sd_available = bool(ytdlp_result.get('success') and ytdlp_result.get('sd_available'))

    if not hd_available and not sd_available:
        return {'success': False, 'error': 'ভিডিও পাওয়া যায়নি বা ডাউনলোড লিংক বের করা যায়নি।'}

    # টাইটেল/থাম্বনেইল যেকোনো একটা source থেকে যা পাওয়া যায় তা দিয়ে সাজানো হয়,
    # RapidAPI সফল হলে সেটাকে অগ্রাধিকার দেওয়া হয়।
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

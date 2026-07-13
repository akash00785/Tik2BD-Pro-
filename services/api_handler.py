import requests
import logging
from config import key_manager, TIMEOUT
from services import rapidapi_cache
from services.ytdlp_handler import fetch_ytdlp_preview


def _fetch_via_rapidapi_cached(video_url):
    """
    _fetch_via_rapidapi()-এর ফলাফল অল্প সময়ের জন্য ক্যাশ করে রাখে।
    """
    cached = rapidapi_cache.get_cached(video_url)
    if cached is not None:
        logging.info(f"RAPIDAPI_CACHE_HIT (no quota used): {video_url}")
        return cached

    logging.info(f"RAPIDAPI_CALL (quota used): {video_url}")
    result = _fetch_via_rapidapi(video_url)
    rapidapi_cache.set_cached(video_url, result)
    return result


def _fetch_via_rapidapi(video_url):
    """
    RapidAPI key ব্যবহার করে HD ডাউনলোড লিংক ও ফটো স্লাইডশো ডেটা আনা।
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

            if response.status_code != 200:
                logging.error(f"API returned status {response.status_code} for URL: {video_url}")
                continue

            try:
                result = response.json()
            except ValueError:
                logging.error("API returned non-JSON response.")
                continue

            if result.get('code') == 0:
                d = result.get('data', {})

                if d.get('images'):
                    return {
                        'success': True,
                        'is_photo': True,
                        'images': d.get('images'),
                        'title': d.get('title') or "TikTok Photos",
                        'author': d.get('author', {}).get('unique_id') or "Unknown"
                    }

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
    প্রথমে yt-dlp দিয়ে প্রিভিউ আনার চেষ্টা করা হয় — এতে RapidAPI কোটা বাঁচে।
    yt-dlp ব্যর্থ হলে তখনই RapidAPI ব্যবহার করা হয় (fallback)।

    - Normal ভিডিও: yt-dlp দিয়ে thumbnail/title/author আনা হয়।
    - ফটো পোস্ট: yt-dlp দিয়ে ছবিগুলো আনা হয়।
    - HD লিংক: শুধু /hd/resolve-এ (HD বাটনে ক্লিক করলে) RapidAPI ডাকা হয়।
    - Normal ডাউনলোড: yt-dlp দিয়েই করা হয়, RapidAPI লাগে না।
    """
    ytdlp_result = fetch_ytdlp_preview(video_url)

    if ytdlp_result.get('success'):
        # yt-dlp সফল হয়েছে

        # ফটো স্লাইডশো
        if ytdlp_result.get('is_photo'):
            logging.info(f"yt-dlp photo slideshow detected: {video_url}")
            return ytdlp_result

        # Regular video — প্রিভিউ তথ্য পাওয়া গেছে
        # sd_url দেওয়া হচ্ছে না — Normal ডাউনলোড /normal/resolve-এ yt-dlp দিয়ে হবে
        logging.info(f"yt-dlp preview success: {video_url}")
        return {
            'success': True,
            'is_photo': False,
            'hd_available': True,
            'sd_available': ytdlp_result.get('sd_available', False),
            # sd_url intentionally omitted — frontend will call /normal/resolve
            'thumbnail': ytdlp_result.get('thumbnail', ''),
            'title': ytdlp_result.get('title', 'Untitled Video'),
            'author': ytdlp_result.get('author', 'Unknown'),
            'duration': ytdlp_result.get('duration', 0),
        }

    else:
        # yt-dlp ব্যর্থ (TikTok ব্লক করেছে বা অন্য সমস্যা) — RapidAPI fallback
        logging.warning(f"yt-dlp failed ({ytdlp_result.get('error')}), falling back to RapidAPI for: {video_url}")
        api_result = _fetch_via_rapidapi_cached(video_url)

        if not api_result.get('success') or api_result.get('is_photo'):
            return api_result

        # RapidAPI থেকে ভিডিও তথ্য পাওয়া গেছে
        hd_url = api_result.get('hd_url')
        sd_url = api_result.get('sd_url')
        return {
            'success': True,
            'is_photo': False,
            'hd_available': bool(hd_url),
            'hd_url': hd_url,
            'sd_available': bool(sd_url),
            'sd_url': sd_url,
            'thumbnail': api_result.get('thumbnail', ''),
            'title': api_result.get('title', 'Untitled Video'),
            'author': api_result.get('author', 'Unknown'),
            'duration': api_result.get('duration', 0),
        }


def resolve_hd_link(video_url):
    """
    ব্যবহারকারী সত্যিই HD Download বাটনে ক্লিক করলে তখনই এটা ডাকা হয় —
    এখানেই আসলে RapidAPI-কে কল করা হয় (cache-সহ)।
    যারা শুধু প্রিভিউ দেখে HD ডাউনলোড করে না, তাদের জন্য কোটা খরচ হয় না।
    """
    logging.info(f"HD_RESOLVE_CLICKED: {video_url}")
    api_result = _fetch_via_rapidapi_cached(video_url)

    if not api_result.get('success'):
        return {'success': False, 'error': api_result.get('error') or 'HD লিংক পাওয়া যায়নি।'}

    hd_url = api_result.get('hd_url')
    if not hd_url:
        return {'success': False, 'error': 'এই ভিডিওর জন্য HD লিংক পাওয়া যায়নি।'}

    return {'success': True, 'hd_url': hd_url}

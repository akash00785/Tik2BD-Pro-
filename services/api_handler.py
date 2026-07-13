import requests
import logging
from config import key_manager, TIMEOUT
from services import rapidapi_cache


def _fetch_via_rapidapi_cached(video_url):
    """
    _fetch_via_rapidapi()-এর ফলাফল অল্প সময়ের জন্য ক্যাশ করে রাখে —
    একই ভিডিও লিংক ঘনঘন/বহুবার এলে প্রতিবার RapidAPI কোটা খরচ না করে।
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
    আগে normal ভিডিওর প্রিভিউ RapidAPI কোটা বাঁচাতে yt-dlp দিয়ে আনা হতো
    (RapidAPI শুধু HD বাটনে ক্লিক করলে ডাকা হতো)। কিন্তু TikTok এখন
    Render-এর মতো ডেটাসেন্টার/ক্লাউড IP থেকে yt-dlp-এর ওয়েবপেজ-info
    রিকোয়েস্টও ব্লক করে দিচ্ছে — ফলে সব normal ভিডিও সার্চে (আসল ভিডিও
    পাবলিক থাকলেও) "প্রাইভেট বা পাওয়া যায়নি" এরর আসছিল। RapidAPI নিজের
    ক্রেডেনশিয়াল দিয়ে কল করে বলে datacenter IP থেকেও ব্লক হয় না, তাই
    এখন preview + HD + Normal (SD) — সবকিছুর জন্যই একবারে RapidAPI-কেই
    (cache-সহ) সরাসরি ডাকা হয়, ভিডিও হোক বা ফটো।
    """
    api_result = _fetch_via_rapidapi_cached(video_url)

    if not api_result.get('success') or api_result.get('is_photo'):
        return api_result

    # HD এবং Normal (SD) দুটো লিংকই RapidAPI থেকে এসেছে, দুটোই TikTok-এর
    # নিজস্ব CDN হোস্ট — তাই দুটোই সরাসরি ব্যবহারকারীর ব্রাউজার থেকে
    # ওপেন করা যায় (bandwidth-free), Render সার্ভারের মধ্য দিয়ে না গিয়ে।
    hd_url = api_result.get('hd_url')
    sd_url = api_result.get('sd_url')
    return {
        'success': True,
        'is_photo': False,
        'hd_available': bool(hd_url),
        'hd_url': hd_url,
        'sd_available': bool(sd_url),
        'sd_url': sd_url,
        'thumbnail': api_result.get('thumbnail'),
        'title': api_result.get('title') or 'Untitled Video',
        'author': api_result.get('author') or 'Unknown',
        'duration': api_result.get('duration') or 0,
    }


def resolve_hd_link(video_url):
    """
    ব্যবহারকারী সত্যিই HD Download বাটনে ক্লিক করলে তখনই এটা ডাকা হয় —
    এখানেই আসলে RapidAPI-কে কল করা হয় (cache-সহ), তাই যারা শুধু প্রিভিউ
    দেখে ডাউনলোড করে না তাদের জন্য কোটা খরচ হয় না।
    Returns dict: {'success': True, 'hd_url': ...} বা {'success': False, 'error': ...}
    """
    logging.info(f"HD_RESOLVE_CLICKED: {video_url}")
    api_result = _fetch_via_rapidapi_cached(video_url)

    if not api_result.get('success'):
        return {'success': False, 'error': api_result.get('error') or 'HD লিংক পাওয়া যায়নি।'}

    hd_url = api_result.get('hd_url')
    if not hd_url:
        return {'success': False, 'error': 'এই ভিডিওর জন্য HD লিংক পাওয়া যায়নি।'}

    return {'success': True, 'hd_url': hd_url}

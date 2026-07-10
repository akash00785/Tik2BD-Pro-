import requests
import logging
from config import key_manager, TIMEOUT
from services.ytdlp_handler import fetch_ytdlp_preview
from services import rapidapi_cache


def _fetch_via_rapidapi_cached(video_url):
    """
    _fetch_via_rapidapi()-এর ফলাফল অল্প সময়ের জন্য ক্যাশ করে রাখে —
    একই ভিডিও লিংক ঘনঘন/বহুবার এলে প্রতিবার RapidAPI কোটা খরচ না করে।
    """
    cached = rapidapi_cache.get_cached(video_url)
    if cached is not None:
        return cached

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


def _looks_like_photo_url(video_url):
    """টিকটকের ফটো/স্লাইডশো পোস্টের URL-এ '/photo/' থাকে (ভিডিওতে '/video/')।
    এটা RapidAPI না ডেকেই মোটামুটি নিশ্চিতভাবে বলে দেয় ফটো পোস্ট কিনা —
    শুধু vm/vt.tiktok.com শর্ট লিংকে এটা বলা যায় না, ওগুলো RapidAPI দিয়েই
    resolve করতে হয় (পুরনো ব্যবহার, বিরল কেস)।"""
    return '/photo/' in (video_url or '').lower()


def fetch_tiktok_data(video_url):
    """
    HD ডাউনলোড RapidAPI key দিয়ে আসে, Normal ডাউনলোড yt-dlp দিয়ে —
    এই দুইটা এখন একে অপরের থেকে স্বাধীন। ফলে RapidAPI-এর সব key মেয়াদ
    ফুরিয়ে গেলে বা exhausted হয়ে গেলেও Normal Download কাজ করবে,
    শুধু HD Download সেই সময়ের জন্য অনুপলব্ধ থাকবে।

    RapidAPI কোটা বাঁচানোর জন্য: সাধারণ ভিডিও লিংকে এই ধাপে RapidAPI-কে
    ডাকা হয় না — শুধু yt-dlp দিয়ে প্রিভিউ আনা হয়, HD লিংক আসলে "resolve"
    হয় যখন ব্যবহারকারী সত্যিই HD Download বাটনে ক্লিক করে (দেখুন
    resolve_hd_link, যেটা /hd/resolve endpoint থেকে ডাকা হয়)। এতে যারা
    শুধু প্রিভিউ দেখে কিন্তু ডাউনলোড করে না, তাদের জন্য কোটা খরচ হয় না।
    ফটো/স্লাইডশো পোস্টের জন্য RapidAPI এখনো এই ধাপেই লাগে, কারণ ছবিগুলোর
    লিংক ছাড়া প্রিভিউই দেখানো যায় না।
    """
    if _looks_like_photo_url(video_url):
        api_result = _fetch_via_rapidapi_cached(video_url)
        if api_result.get('success') and api_result.get('is_photo'):
            return api_result
        # '/photo/' থাকলেও RapidAPI যদি ছবি না দিয়ে ভিডিও/এরর দেয়, নিচের
        # সাধারণ ভিডিও ফ্লো-তে পড়ে যাবে (video_url আবার resolve হবে না,
        # ytdlp_result দিয়েই চলবে)।
        if not api_result.get('success'):
            ytdlp_result = fetch_ytdlp_preview(video_url)
            if not ytdlp_result.get('success'):
                return api_result if api_result.get('error') else ytdlp_result
            return _build_lazy_hd_result(video_url, ytdlp_result)

    ytdlp_result = fetch_ytdlp_preview(video_url)

    if not ytdlp_result.get('success'):
        return ytdlp_result

    return _build_lazy_hd_result(video_url, ytdlp_result)


def _build_lazy_hd_result(video_url, ytdlp_result):
    """RapidAPI-কে না ডেকে, আশাবাদীভাবে (optimistic) HD বাটন দেখানোর জন্য
    রেজাল্ট বানায়। আসল HD লিংক ও তার সত্যিকারের availability বের হবে
    resolve_hd_link() কল করার সময় (ব্যবহারকারী HD বাটনে ক্লিক করলে)।"""
    sd_available = bool(ytdlp_result.get('sd_available'))

    if not sd_available:
        # yt-dlp SD দিতে না পারলেও HD থাকতে পারে (RapidAPI বাদে yt-dlp
        # ব্যর্থ হতে পারে) — তাই এখানেই পুরোপুরি ফেইল না ঘোষণা করে HD-এর
        # সুযোগও খোলা রাখা হচ্ছে, resolve করার সময় বোঝা যাবে সত্যিই কিছু
        # পাওয়া যায় কিনা।
        pass

    return {
        'success': True,
        'is_photo': False,
        'hd_available': True,
        'hd_pending': True,   # ফ্রন্টএন্ডকে বলে: আসল HD লিংক এখনো resolve হয়নি
        'hd_url': None,
        'sd_available': sd_available,
        'video_url': video_url if sd_available else None,
        'thumbnail': ytdlp_result.get('thumbnail'),
        'title': ytdlp_result.get('title') or 'Untitled Video',
        'author': ytdlp_result.get('author') or 'Unknown',
        'duration': ytdlp_result.get('duration') or 0,
    }


def resolve_hd_link(video_url):
    """
    ব্যবহারকারী সত্যিই HD Download বাটনে ক্লিক করলে তখনই এটা ডাকা হয় —
    এখানেই আসলে RapidAPI-কে কল করা হয় (cache-সহ), তাই যারা শুধু প্রিভিউ
    দেখে ডাউনলোড করে না তাদের জন্য কোটা খরচ হয় না।
    Returns dict: {'success': True, 'hd_url': ...} বা {'success': False, 'error': ...}
    """
    api_result = _fetch_via_rapidapi_cached(video_url)

    if not api_result.get('success'):
        return {'success': False, 'error': api_result.get('error') or 'HD লিংক পাওয়া যায়নি।'}

    hd_url = api_result.get('hd_url')
    if not hd_url:
        return {'success': False, 'error': 'এই ভিডিওর জন্য HD লিংক পাওয়া যায়নি।'}

    return {'success': True, 'hd_url': hd_url}

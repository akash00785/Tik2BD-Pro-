import logging
import yt_dlp
from yt_dlp.utils import sanitized_Request

# TikTok CDN নির্দিষ্ট User-Agent/Referer না থাকলে 403 Forbidden দেয়।
# fallback হিসেবে ব্যবহার হয় যদি yt-dlp নিজের http_headers না দেয়।
DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'
    ),
    'Referer': 'https://www.tiktok.com/',
}

_YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'noplaylist': True,
}


def _quality_key(f):
    """
    TikTok formats-এ 'height' প্রায়ই ভুল/একই রকম রিপোর্ট হয়, তাই
    filesize/bitrate অনুযায়ী sort করা হয়। watermark ছাড়া মূল ফাইলটিকে
    (format_id/format_note এ "download" থাকে) সবচেয়ে বেশি priority দেওয়া হয়।
    """
    label = f"{f.get('format_id') or ''} {f.get('format_note') or ''}".lower()
    no_watermark_bonus = 1 if 'download' in label else 0
    return (
        no_watermark_bonus,
        f.get('filesize') or f.get('filesize_approx') or 0,
        f.get('tbr') or 0,
        f.get('height') or 0,
    )


def _av_formats(info):
    formats = info.get('formats') or []
    av = [
        f for f in formats
        if f.get('url')
        and f.get('vcodec') != 'none'
        and f.get('acodec') != 'none'
    ]
    av.sort(key=_quality_key, reverse=True)
    return av


def _headers_for(obj, info):
    headers = dict(DEFAULT_HEADERS)
    if info and info.get('http_headers'):
        headers.update(info['http_headers'])
    if obj and obj.get('http_headers'):
        headers.update(obj['http_headers'])
    return headers


def fetch_ytdlp_preview(video_url):
    """
    yt-dlp দিয়ে ভিডিওর প্রিভিউ তথ্য (title, author, thumbnail) এবং normal
    কোয়ালিটি ডাউনলোডের জন্য availability বের করা। এটা RapidAPI key-এর
    উপর নির্ভর করে না, তাই key মেয়াদ ফুরিয়ে গেলেও "Normal Download" কাজ করবে।
    """
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except yt_dlp.utils.DownloadError as e:
        logging.error(f"yt-dlp preview DownloadError: {e}")
        return {'success': False, 'error': 'ভিডিওটি প্রাইভেট বা পাওয়া যায়নি।'}
    except Exception as e:
        logging.error(f"yt-dlp preview unexpected error: {e}")
        return {'success': False, 'error': 'yt-dlp দিয়ে ভিডিও প্রসেস করতে সমস্যা হয়েছে।'}

    if not info:
        return {'success': False, 'error': 'yt-dlp: কোনো তথ্য পাওয়া যায়নি।'}

    av = _av_formats(info)
    sd_available = bool(av) or bool(info.get('url'))

    return {
        'success': True,
        'sd_available': sd_available,
        'title': info.get('title') or 'Untitled Video',
        'author': info.get('uploader') or info.get('uploader_id') or 'Unknown',
        'thumbnail': info.get('thumbnail') or '',
        'duration': info.get('duration') or 0,
    }


def resolve_normal_link(video_url):
    """
    Normal/SD ডাউনলোডের জন্য সরাসরি CDN URL বের করে দেয় (স্ট্রিম করে না) —
    ব্রাউজার নিজে সরাসরি এই লিংকে গিয়ে ভিডিওটা আনবে, তাই আমাদের সার্ভারের
    কোনো bandwidth খরচ হবে না। TikTok CDN আমাদের সার্ভারের (ডেটা-সেন্টার)
    IP থেকে আসা রিকোয়েস্ট প্রায়ই 403 করে দেয়, কিন্তু সাধারণ ব্যবহারকারীর
    ব্রাউজার/মোবাইল থেকে এই একই লিংকে অনুরোধ গেলে TikTok সেটা আটকায় না।

    ট্রেড-অফ: cross-origin URL-এ ব্রাউজারের <a download> অ্যাট্রিবিউট কাজ
    করে না, তাই লিংকটা নতুন ট্যাবে ভিডিও চালিয়ে দেয় — ব্যবহারকারীকে
    ম্যানুয়ালি (থ্রি-ডট মেনু থেকে) "Save video" করতে হয়।

    Returns: {'success': True, 'normal_url': url} বা {'success': False, 'error': ...}
    """
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except yt_dlp.utils.DownloadError as e:
        logging.error(f"resolve_normal_link DownloadError: {e}")
        return {'success': False, 'error': 'ভিডিওটি প্রাইভেট বা পাওয়া যায়নি।'}
    except Exception as e:
        logging.error(f"resolve_normal_link unexpected error: {e}")
        return {'success': False, 'error': 'yt-dlp দিয়ে ভিডিও প্রসেস করতে সমস্যা হয়েছে।'}

    if not info:
        return {'success': False, 'error': 'yt-dlp: কোনো তথ্য পাওয়া যায়নি।'}

    av = _av_formats(info)
    if av:
        # normal/SD কোয়ালিটি: সবচেয়ে ছোট available format, একটাই থাকলে সেটাই।
        obj = av[-1] if len(av) > 1 else av[0]
    elif info.get('url'):
        obj = info
    else:
        return {'success': False, 'error': 'এই ভিডিওর জন্য Normal কোয়ালিটি পাওয়া যায়নি।'}

    url = obj.get('url')
    if not url:
        return {'success': False, 'error': 'এই ভিডিওর জন্য Normal কোয়ালিটি পাওয়া যায়নি।'}

    return {'success': True, 'normal_url': url}


def stream_ytdlp_video(video_url):
    """
    normal/SD ভিডিওটা yt-dlp-এর নিজের opener (ydl.urlopen) দিয়ে CDN থেকে
    স্ট্রিম করা হয় — কারণ TikTok CDN শুধু matching headers দেখেই রাজি হয়
    না, extraction session-এর cookie (msToken/ttwid) লাগে। তাই raw
    `requests.get()` ব্যবহার করা হয়নি।

    Returns: (ydl, cdn_response) or None
    """
    ydl = yt_dlp.YoutubeDL(_YDL_OPTS)
    try:
        info = ydl.extract_info(video_url, download=False)
    except Exception as e:
        logging.error(f"stream_ytdlp_video extract error: {e}")
        ydl.close()
        return None

    if not info:
        ydl.close()
        return None

    av = _av_formats(info)
    if av:
        # normal/SD কোয়ালিটি: সবচেয়ে ছোট available format, একটাই থাকলে সেটাই।
        obj = av[-1] if len(av) > 1 else av[0]
    elif info.get('url'):
        obj = info
    else:
        ydl.close()
        return None

    url = obj.get('url')
    if not url:
        ydl.close()
        return None

    headers = _headers_for(obj, info)
    try:
        req = sanitized_Request(url, headers=headers)
        cdn_resp = ydl.urlopen(req)
    except Exception as e:
        logging.error(f"stream_ytdlp_video urlopen error: {e}")
        ydl.close()
        return None

    return ydl, cdn_resp

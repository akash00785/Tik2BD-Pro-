import logging
import yt_dlp

# TikTok CDN-এর জন্য প্রয়োজনীয় headers — এগুলো ছাড়া 403 Forbidden আসে
DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.tiktok.com/',
}

# yt-dlp options — TikTok-এর বট ডিটেকশন এড়াতে উন্নত সেটিংস
_YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'noplaylist': True,
    'socket_timeout': 30,
    'retries': 3,
    'fragment_retries': 3,
    'http_headers': DEFAULT_HEADERS,
    # TikTok-specific: app simulation যাতে বট ডিটেকশন এড়ানো যায়
    'extractor_args': {
        'tiktok': {
            'app_name': ['trill'],
        }
    },
}


def _quality_key(f):
    """
    TikTok formats sort করার জন্য key।
    watermark ছাড়া মূল ফাইলকে সবচেয়ে বেশি priority।
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
    """
    Audio+Video সহ formats বের করে। TikTok কখনো কখনো acodec ঠিকমতো
    tag করে না, তাই ধাপে ধাপে fallback করা হয়।
    """
    formats = info.get('formats') or []

    # প্রথম চেষ্টা: audio এবং video উভয়ই আছে
    av = [
        f for f in formats
        if f.get('url')
        and f.get('vcodec') not in ('none', None, '')
        and f.get('acodec') not in ('none', None, '')
    ]

    # দ্বিতীয় চেষ্টা: শুধু video codec আছে (TikTok audio কখনো tag করে না)
    if not av:
        av = [
            f for f in formats
            if f.get('url')
            and f.get('vcodec') not in ('none', None, '')
        ]

    # তৃতীয় চেষ্টা: URL আছে এমন যেকোনো format
    if not av:
        av = [f for f in formats if f.get('url')]

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
    yt-dlp দিয়ে ভিডিওর প্রিভিউ তথ্য (title, author, thumbnail) এবং
    normal quality ডাউনলোডের availability বের করা।
    RapidAPI key-এর উপর নির্ভর করে না।
    """
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except yt_dlp.utils.DownloadError as e:
        err_msg = str(e)
        logging.error(f"yt-dlp preview DownloadError: {err_msg}")
        if 'private' in err_msg.lower():
            return {'success': False, 'error': 'ভিডিওটি প্রাইভেট।'}
        return {'success': False, 'error': 'ভিডিওটি পাওয়া যায়নি বা ডাউনলোড করা সম্ভব নয়।'}
    except Exception as e:
        logging.error(f"yt-dlp preview unexpected error: {e}")
        return {'success': False, 'error': 'ভিডিও প্রসেস করতে সমস্যা হয়েছে।'}

    if not info:
        return {'success': False, 'error': 'yt-dlp: কোনো তথ্য পাওয়া যায়নি।'}

    av = _av_formats(info)
    sd_available = bool(av) or bool(info.get('url'))

    # সরাসরি CDN URL বের করা — ব্যান্ডউইথ বাঁচাতে ব্রাউজারে পাঠানো হবে
    sd_url = ''
    if av:
        best = av[-1] if len(av) > 1 else av[0]
        sd_url = best.get('url', '')
    elif info.get('url'):
        sd_url = info.get('url', '')

    return {
        'success': True,
        'sd_available': sd_available,
        'sd_url': sd_url,
        'title': info.get('title') or 'Untitled Video',
        'author': info.get('uploader') or info.get('uploader_id') or 'Unknown',
        'thumbnail': info.get('thumbnail') or '',
        'duration': info.get('duration') or 0,
    }


def stream_ytdlp_video(video_url):
    """
    Normal ভিডিও — yt-dlp দিয়ে CDN URL extract করে, তারপর
    Python requests দিয়ে stream করা হয়।
    ydl.urlopen() এর বদলে requests ব্যবহার — বেশি reliable।

    Returns: (requests.Response, cdn_url) or None
    """
    import requests as _req

    ydl = yt_dlp.YoutubeDL(_YDL_OPTS)
    try:
        info = ydl.extract_info(video_url, download=False)
    except Exception as e:
        logging.error(f"stream_ytdlp_video extract error: {e}")
        return None
    finally:
        ydl.close()

    if not info:
        return None

    av = _av_formats(info)

    if av:
        obj = av[0]
    elif info.get('url'):
        obj = info
    else:
        return None

    cdn_url = obj.get('url')
    if not cdn_url:
        return None

    # yt-dlp এর extracted headers + default headers merge করা
    headers = _headers_for(obj, info)

    try:
        resp = _req.get(cdn_url, headers=headers, stream=True, timeout=60)
        resp.raise_for_status()
        return resp, cdn_url
    except Exception as e:
        logging.error(f"stream_ytdlp_video requests error: {e}")
        return None

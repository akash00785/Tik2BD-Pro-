import logging
import yt_dlp
from yt_dlp.utils import sanitized_Request

# TikTok CDN নির্দিষ্ট User-Agent/Referer না থাকলে 403 Forbidden দেয়।
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

# ফটো স্লাইডশো পোস্টের জন্য noplaylist=False দরকার
_YDL_OPTS_PHOTO = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'noplaylist': False,
}


def _quality_key(f):
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


def _extract_photo_images(info):
    """
    TikTok ফটো স্লাইডশো পোস্ট থেকে ছবির URL গুলো বের করা।
    yt-dlp ফটো পোস্টকে playlist হিসেবে রিটার্ন করে, entries-এ প্রতিটা ছবি থাকে।
    """
    entries = info.get('entries') or []
    images = []

    for entry in entries:
        if not entry:
            continue
        # প্রতিটা entry-তে url বা formats থাকতে পারে
        url = entry.get('url') or ''
        ext = (entry.get('ext') or '').lower()
        vcodec = entry.get('vcodec') or ''
        acodec = entry.get('acodec') or ''

        # Image entry: video codec নেই, বা image extension আছে
        if url and (
            ext in ('jpg', 'jpeg', 'png', 'webp', 'heic')
            or (vcodec == 'none' and acodec == 'none')
            or (vcodec == 'none' and not acodec)
        ):
            images.append(url)
        elif not url:
            # formats থেকে চেষ্টা করা
            for fmt in (entry.get('formats') or []):
                furl = fmt.get('url') or ''
                fext = (fmt.get('ext') or '').lower()
                if furl and fext in ('jpg', 'jpeg', 'png', 'webp', 'heic'):
                    images.append(furl)
                    break

    return images


def fetch_ytdlp_preview(video_url):
    """
    yt-dlp দিয়ে ভিডিওর প্রিভিউ তথ্য (title, author, thumbnail) এবং
    normal কোয়ালিটি ডাউনলোডের জন্য availability বের করা।
    TikTok ফটো স্লাইডশো পোস্টও ডিটেক্ট করে।

    API key-এর উপর নির্ভর করে না — key মেয়াদ ফুরিয়ে গেলেও কাজ করবে।
    """
    # প্রথমে noplaylist=False দিয়ে চেষ্টা — ফটো পোস্টের জন্য দরকার
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS_PHOTO) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except yt_dlp.utils.DownloadError as e:
        logging.error(f"yt-dlp preview DownloadError: {e}")
        return {'success': False, 'error': 'ভিডিওটি প্রাইভেট বা পাওয়া যায়নি।'}
    except Exception as e:
        logging.error(f"yt-dlp preview unexpected error: {e}")
        return {'success': False, 'error': 'yt-dlp দিয়ে ভিডিও প্রসেস করতে সমস্যা হয়েছে।'}

    if not info:
        return {'success': False, 'error': 'yt-dlp: কোনো তথ্য পাওয়া যায়নি।'}

    # ফটো স্লাইডশো চেক: entries আছে কিনা
    if info.get('entries') is not None:
        images = _extract_photo_images(info)
        if images:
            return {
                'success': True,
                'is_photo': True,
                'images': images,
                'title': info.get('title') or 'TikTok Photos',
                'author': info.get('uploader') or info.get('uploader_id') or 'Unknown',
            }

    # Normal video
    av = _av_formats(info)
    sd_available = bool(av) or bool(info.get('url'))

    return {
        'success': True,
        'is_photo': False,
        'sd_available': sd_available,
        'title': info.get('title') or 'Untitled Video',
        'author': info.get('uploader') or info.get('uploader_id') or 'Unknown',
        'thumbnail': info.get('thumbnail') or '',
        'duration': info.get('duration') or 0,
    }


def resolve_normal_link(video_url):
    """
    Normal/SD ডাউনলোডের জন্য সরাসরি CDN URL বের করে দেয় —
    ব্রাউজার নিজে সরাসরি এই লিংকে গিয়ে ভিডিওটা আনবে।
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
    normal/SD ভিডিওটা yt-dlp-এর নিজের opener দিয়ে CDN থেকে স্ট্রিম করা।
    TikTok CDN শুধু matching headers দেখেই রাজি হয় না, extraction
    session-এর cookie লাগে — তাই একই yt-dlp session দিয়েই ডাউনলোড করা হয়।

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

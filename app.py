from flask import Flask, render_template, request, jsonify, Response, stream_with_context, g
import os
import secrets
from urllib.parse import urlparse, quote
import requests as req_lib
from services.api_handler import fetch_tiktok_data
from services.rapidapi_cache import get_cached, set_cached
from services.rapidapi_cache import get_cached, set_cached
from services.ytdlp_handler import stream_ytdlp_video
from services import hd_limiter
from utils.validators import is_valid_tiktok_url
from services.logger import logger
import ads_config

app = Flask(__name__, template_folder='templates', static_folder='static')

DEVICE_COOKIE_NAME = 'tik2bd_device'
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # ১ বছর


def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _get_or_create_device_id():
    existing = request.cookies.get(DEVICE_COOKIE_NAME)
    if existing:
        return existing
    if not hasattr(g, '_new_device_id'):
        g._new_device_id = secrets.token_urlsafe(24)
    return g._new_device_id


@app.after_request
def add_device_cookie(response):
    if not request.cookies.get(DEVICE_COOKIE_NAME) and hasattr(g, '_new_device_id'):
        response.set_cookie(
            DEVICE_COOKIE_NAME,
            g._new_device_id,
            max_age=DEVICE_COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',
        )
    return response


ALLOWED_CDN_HOST_SUFFIXES = (
    '.tiktokcdn.com',
    '.tiktokcdn-us.com',
    '.tiktokcdn-eu.com',
    '.tiktokv.com',
    '.tiktokv.us',
    '.muscdn.com',
    '.ibyteimg.com',
    '.byteicdn.com',
    '.tokcdn.com',
    '.byteoversea.com',
    '.akamaized.net',
)


def is_allowed_cdn_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == s.lstrip('.') or host.endswith(s) for s in ALLOWED_CDN_HOST_SUFFIXES)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/download', methods=['POST'])
def download():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request. JSON body required.'}), 400

    video_url = data.get('url', '').strip()

    if not is_valid_tiktok_url(video_url):
        logger.warning(f"Invalid URL attempted: {video_url}")
        return jsonify({'success': False, 'error': 'Invalid TikTok URL provided.'}), 400

    logger.info(f"Processing download request for: {video_url}")

    # ── ৪৫ মিনিট Cache চেক — একই লিঙ্কে বারবার API call বন্ধ ──
    cached = get_cached(video_url)
    if cached:
        logger.info("Cache hit — RapidAPI call বাঁচলো।")
        if not cached.get('is_photo') and cached.get('hd_available'):
            status = hd_limiter.get_status(_client_ip(), _get_or_create_device_id())
            cached['hd_limit'] = status
            if status['locked']:
                cached['hd_available'] = False
                cached['hd_locked'] = True
        return jsonify(cached)

    result = fetch_tiktok_data(video_url)

    if result['success']:
        # সফল হলে cache-এ সেভ করো (৪৫ মিনিট)
        set_cached(video_url, result)
        if not result.get('is_photo') and result.get('hd_available'):
            status = hd_limiter.get_status(_client_ip(), _get_or_create_device_id())
            result['hd_limit'] = status
            if status['locked']:
                result['hd_available'] = False
                result['hd_locked'] = True
        logger.info("Download success.")
        return jsonify(result)
    else:
        logger.error(f"Download failed: {result.get('error')}")
        return jsonify(result), 400


@app.route('/ads/config')
def ads_config_route():
    return jsonify({
        'enabled': ads_config.ads_enabled(),
        'ad_link': ads_config.AD_LINK if ads_config.ads_enabled() else None,
        'wait_seconds': ads_config.AD_WAIT_SECONDS,
        'free_hd_limit': ads_config.FREE_HD_LIMIT,
    })


@app.route('/ads/unlock/start', methods=['POST'])
def ads_unlock_start():
    if not ads_config.ads_enabled():
        return jsonify({'error': 'Ad unlock is not enabled.'}), 400
    device_id = _get_or_create_device_id()
    token = hd_limiter.start_unlock(_client_ip(), device_id)
    return jsonify({'token': token, 'wait_seconds': ads_config.AD_WAIT_SECONDS})


@app.route('/ads/unlock/claim', methods=['POST'])
def ads_unlock_claim():
    if not ads_config.ads_enabled():
        return jsonify({'error': 'Ad unlock is not enabled.'}), 400
    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()
    if not token:
        return jsonify({'error': 'Missing token.'}), 400

    device_id = _get_or_create_device_id()
    success, error = hd_limiter.claim_unlock(token, _client_ip(), device_id, ads_config.AD_WAIT_SECONDS)

    if not success:
        messages = {
            'invalid_token': 'Invalid or expired unlock token.',
            'mismatch': 'This unlock token is not valid for your session.',
            'too_soon': 'Please wait for the ad timer to finish before claiming.',
        }
        return jsonify({'error': messages.get(error, 'Could not unlock.')}), 400

    status = hd_limiter.get_status(_client_ip(), device_id)
    return jsonify({'success': True, 'hd_limit': status})


@app.route('/proxy-download')
def proxy_download():
    """HD ভিডিও প্রক্সি — TikTok CDN URL থেকে সরাসরি ডাউনলোড।"""
    cdn_url = request.args.get('url', '').strip()
    filename = request.args.get('filename', 'tiktok_video.mp4')

    if not cdn_url:
        return jsonify({'error': 'No URL provided'}), 400

    if not is_allowed_cdn_url(cdn_url):
        logger.warning(f"Blocked proxy-download for disallowed host: {cdn_url}")
        return jsonify({'error': 'Invalid URL'}), 400

    allowed, status = hd_limiter.try_consume(_client_ip(), _get_or_create_device_id())
    if not allowed:
        logger.warning("HD download blocked: free limit exhausted.")
        return jsonify({
            'error': 'Daily free HD limit reached. Watch an ad to unlock more, or try again later.',
            'hd_limit': status,
        }), 429

    try:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/125.0.0.0 Safari/537.36'
            ),
            'Referer': 'https://www.tiktok.com/',
        }
        cdn_resp = req_lib.get(cdn_url, headers=headers, stream=True, timeout=60)
        cdn_resp.raise_for_status()

        content_type = cdn_resp.headers.get('Content-Type', 'video/mp4')
        content_length = cdn_resp.headers.get('Content-Length')

        response_headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': content_type,
        }
        if content_length:
            response_headers['Content-Length'] = content_length

        def generate():
            for chunk in cdn_resp.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk

        return Response(
            stream_with_context(generate()),
            headers=response_headers,
            status=200
        )

    except req_lib.Timeout:
        logger.error(f"Proxy timeout for URL: {cdn_url}")
        return jsonify({'error': 'Download timed out. Please try again.'}), 504
    except req_lib.RequestException as e:
        logger.error(f"Proxy error: {str(e)}")
        return jsonify({'error': 'Could not fetch video. Please try again.'}), 502


@app.route('/watch')
def watch():
    """Normal ভিডিও player page — ব্রাউজারে inline play, download নয়।"""
    video_url = request.args.get('url', '').strip()
    if not video_url or not is_valid_tiktok_url(video_url):
        return "Invalid TikTok URL.", 400
    proxy_url = f"/proxy-download-normal?url={quote(video_url, safe='')}&filename=tiktok.mp4"
    return render_template('watch.html', proxy_url=proxy_url)


@app.route('/hd/consume', methods=['POST'])
def hd_consume():
    """
    HD বাটন ক্লিক হলে JS background-এ এই endpoint call করে।
    CDN URL সরাসরি browser-এ খোলা হয় (server bandwidth নেই),
    কিন্তু limit এখানে কমানো হয়।
    """
    allowed, status = hd_limiter.try_consume(_client_ip(), _get_or_create_device_id())
    if not allowed:
        return jsonify({'error': 'limit_reached', 'hd_limit': status}), 429
    return jsonify({'ok': True, 'hd_limit': status})


@app.route('/proxy-download-normal')
def proxy_download_normal():
    """
    Normal বাটন — yt-dlp দিয়ে TikTok CDN URL extract করে
    Python requests দিয়ে stream করা হয়।
    RapidAPI key লাগে না।
    """
    video_url = request.args.get('url', '').strip()
    filename = request.args.get('filename', 'tiktok.mp4')

    if not video_url or not is_valid_tiktok_url(video_url):
        return jsonify({'error': 'Invalid request'}), 400

    try:
        result = stream_ytdlp_video(video_url)
    except Exception as e:
        logger.error(f"yt-dlp proxy error: {str(e)}")
        return jsonify({'error': 'Could not fetch video. Please try again.'}), 502

    if not result:
        return jsonify({'error': 'Could not fetch video. Please try again.'}), 502

    cdn_resp, _ = result  # (requests.Response, cdn_url)

    content_type = cdn_resp.headers.get('Content-Type') or 'video/mp4'
    content_length = cdn_resp.headers.get('Content-Length')

    response_headers = {
        'Content-Disposition': f'inline; filename="{filename}"',
        'Content-Type': 'video/mp4',
        'Accept-Ranges': 'none',
        'Cache-Control': 'no-cache',
    }
    if content_length:
        response_headers['Content-Length'] = content_length

    def generate():
        try:
            for chunk in cdn_resp.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        except Exception as e:
            logger.error(f"yt-dlp proxy stream interrupted: {str(e)}")
        finally:
            cdn_resp.close()

    return Response(
        stream_with_context(generate()),
        headers=response_headers,
        status=200
    )


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=port, debug=debug)

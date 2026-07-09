from flask import Flask, render_template, request, jsonify, Response, stream_with_context, g
import os
import secrets
from urllib.parse import urlparse
import requests as req_lib
from services.api_handler import fetch_tiktok_data
from services.ytdlp_handler import stream_ytdlp_video
from services import hd_limiter
from utils.validators import is_valid_tiktok_url
from services.logger import logger
import ads_config

app = Flask(__name__, template_folder='templates', static_folder='static')

DEVICE_COOKIE_NAME = 'tik2bd_device'
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # ১ বছর


def _client_ip():
    # Render/অন্য কোনো রিভার্স প্রক্সির পেছনে থাকলে X-Forwarded-For থাকতে পারে
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _get_or_create_device_id():
    """
    কুকি থেকে device id পড়ে; না থাকলে নতুন একটা বানিয়ে request-এর
    জন্য `flask.g`-তে রেখে দেয়, যাতে একই রিকোয়েস্টে limiter সঠিক
    id-টাই পায়, এবং রেসপন্সে সেই id-টাই কুকি হিসেবে সেভ হয়।
    """
    existing = request.cookies.get(DEVICE_COOKIE_NAME)
    if existing:
        return existing
    if not hasattr(g, '_new_device_id'):
        g._new_device_id = secrets.token_urlsafe(24)
    return g._new_device_id


@app.after_request
def add_device_cookie(response):
    """প্রতিটা ভিজিটরের জন্য একটা দীর্ঘস্থায়ী, র‍্যান্ডম device কুকি বসানো হয় —
    এটাই HD লিমিট গণনার সময় IP-এর সাথে মিলিয়ে ব্যবহার করা হয়।"""
    if not request.cookies.get(DEVICE_COOKIE_NAME) and hasattr(g, '_new_device_id'):
        response.set_cookie(
            DEVICE_COOKIE_NAME,
            g._new_device_id,
            max_age=DEVICE_COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',
        )
    return response

# TikTok-এর নিজস্ব CDN হোস্টগুলো (RapidAPI যে hd/sd লিংক ফেরত দেয়, সেগুলো
# এই ডোমেইনগুলোর কোনো একটার সাব-ডোমেইন থেকে আসে)।
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
)


def is_allowed_cdn_url(url):
    """http(s) এবং TikTok CDN হোস্ট ছাড়া অন্য কোনো URL অনুমোদিত না —
    এটা /proxy-download-কে open proxy হয়ে যাওয়া থেকে রক্ষা করে।"""
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
    """হোম পেজ রেন্ডার করা"""
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    """ভিডিও ডাউনলোডের মেইন API এন্ডপয়েন্ট"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request. JSON body required.'}), 400

    video_url = data.get('url', '').strip()

    if not is_valid_tiktok_url(video_url):
        logger.warning(f"Invalid URL attempted: {video_url}")
        return jsonify({'success': False, 'error': 'Invalid TikTok URL provided.'}), 400

    logger.info(f"Processing download request for: {video_url}")
    result = fetch_tiktok_data(video_url)

    if result['success']:
        # HD-এর অবশিষ্ট ফ্রি লিমিট সবসময় মেটাডেটার সাথে পাঠানো হয় (শুধু
        # লক হলে না) — যাতে ফ্রন্টএন্ড প্রতিবার "৪/৫ বাকি" জাতীয় কাউন্ট
        # দেখাতে পারে, এবং লিমিট শেষ হলেই (৫ম ডাউনলোডের পরে) "লক" অবস্থা +
        # অ্যাড দেখাতে পারে। আসল কনজিউম হয় /proxy-download-এ, যখন
        # ব্যবহারকারী সত্যিই ফাইলটা নেয় — এখানে শুধু স্ট্যাটাস চেক হয়।
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
    """ফ্রন্টএন্ড এটা দিয়ে বুঝবে অ্যাড-গেট চালু আছে কিনা এবং কতক্ষণ অপেক্ষা করতে হবে।"""
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
    """
    TikTok CDN URL প্রক্সি করে সরাসরি ডাউনলোড করানো।
    কারণ: ব্রাউজার cross-origin URL-এ <a download> অ্যাট্রিবিউট কাজ করে না,
    ভিডিও প্লে হয়ে যায়। এই endpoint সার্ভার থেকে ফাইল নামিয়ে
    Content-Disposition: attachment হেডার দিয়ে পাঠায়।
    """
    cdn_url = request.args.get('url', '').strip()
    filename = request.args.get('filename', 'tiktok_video.mp4')

    if not cdn_url:
        return jsonify({'error': 'No URL provided'}), 400

    # শুধু http/https URL অনুমোদিত, এবং শুধু TikTok-এর নিজস্ব CDN হোস্ট —
    # নাহলে এই endpoint যেকোনো URL fetch করে দেওয়ার একটা "open proxy"
    # হয়ে যায়, যা আক্রমণকারীরা আমাদের সার্ভারকে bandwidth relay বা
    # নিজের পরিচয় আড়াল করার হাতিয়ার হিসেবে ব্যবহার করতে পারত।
    if not is_allowed_cdn_url(cdn_url):
        logger.warning(f"Blocked proxy-download for disallowed host: {cdn_url}")
        return jsonify({'error': 'Invalid URL'}), 400

    # HD ফ্রি লিমিট এখানেই আসলে "consume" করা হয় (মেটাডেটা রেসপন্সে না) —
    # কারণ এটাই আসল ফাইল ডাউনলোডের মুহূর্ত। এটা সরাসরি এই route হিট করেও
    # (ফ্রন্টএন্ড বাইপাস করে) কেউ লিমিট এড়াতে পারবে না।
    allowed, status = hd_limiter.try_consume(_client_ip(), _get_or_create_device_id())
    if not allowed:
        logger.warning("HD download blocked: free limit + unlock grants exhausted.")
        return jsonify({
            'error': 'Daily free HD limit reached. Watch an ad to unlock more, or try again later.',
            'hd_limit': status,
        }), 429

    try:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
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


@app.route('/proxy-download-normal')
def proxy_download_normal():
    """
    Normal (SD) ডাউনলোড — yt-dlp দিয়ে সরাসরি TikTok পোস্ট URL থেকে স্ট্রিম
    করা হয়, RapidAPI key-এর উপর নির্ভর না করে। HD-এর মতো এখানে CDN URL
    ব্যবহার করা হয় না, কারণ yt-dlp-এর তোলা CDN URL-এ raw requests দিয়ে
    হিট করলে TikTok 403 Forbidden দেয় — extraction session-এর cookie
    (msToken/ttwid) ছাড়া CDN রাজি হয় না। তাই একই yt-dlp session
    (cookiejar) দিয়েই ডাউনলোড করা হয়।
    """
    video_url = request.args.get('url', '').strip()
    filename = request.args.get('filename', 'tiktok_normal.mp4')

    if not video_url or not is_valid_tiktok_url(video_url):
        return jsonify({'error': 'Invalid request'}), 400

    try:
        result = stream_ytdlp_video(video_url)
    except Exception as e:
        logger.error(f"yt-dlp proxy error: {str(e)}")
        return jsonify({'error': 'Could not fetch video. Please try again.'}), 502

    if not result:
        return jsonify({'error': 'Could not fetch video. Please try again.'}), 502

    ydl, cdn_resp = result

    resp_info = getattr(cdn_resp, 'headers', {}) or {}
    content_type = resp_info.get('Content-Type') or 'video/mp4'
    content_length = resp_info.get('Content-Length')

    response_headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Type': content_type,
    }
    if content_length:
        response_headers['Content-Length'] = content_length

    def generate():
        try:
            while True:
                chunk = cdn_resp.read(65536)
                if not chunk:
                    break
                yield chunk
        except Exception as e:
            logger.error(f"yt-dlp proxy stream interrupted: {str(e)}")
        finally:
            try:
                cdn_resp.close()
            except Exception:
                pass
            ydl.close()

    return Response(
        stream_with_context(generate()),
        headers=response_headers,
        status=200
    )


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=port, debug=debug)

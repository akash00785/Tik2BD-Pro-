from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import os
from urllib.parse import urlparse
import requests as req_lib
from services.api_handler import fetch_tiktok_data
from services.ytdlp_handler import stream_ytdlp_video
from utils.validators import is_valid_tiktok_url
from services.logger import logger

app = Flask(__name__, template_folder='templates', static_folder='static')

# TikTok-এর নিজস্ব CDN হোস্টগুলো (RapidAPI যে hd/sd লিংক ফেরত দেয়, সেগুলো
# এই ডোমেইনগুলোর কোনো একটার সাব-ডোমেইন থেকে আসে)।
ALLOWED_CDN_HOST_SUFFIXES = (
    '.tiktokcdn.com',
    '.tiktokcdn-us.com',
    '.tiktokv.com',
    '.tiktokv.us',
    '.muscdn.com',
    '.ibyteimg.com',
    '.byteicdn.com',
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
        logger.info("Download success.")
        return jsonify(result)
    else:
        logger.error(f"Download failed: {result.get('error')}")
        return jsonify(result), 400


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

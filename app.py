from flask import Flask, render_template, request, jsonify
import os
from services.api_handler import fetch_tiktok_data
from utils.validators import is_valid_tiktok_url
from services.logger import logger

app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route('/')
def home():
    """হোম পেজ রেন্ডার করা"""
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    """ভিডিও ডাউনলোডের মেইন API এন্ডপয়েন্ট"""
    data = request.json
    video_url = data.get('url')

    # ১. URL ভ্যালিডেশন
    if not is_valid_tiktok_url(video_url):
        logger.warning(f"Invalid URL attempted: {video_url}")
        return jsonify({'success': False, 'error': 'Invalid TikTok URL provided.'}), 400

    # ২. API হ্যান্ডলার কল করা
    logger.info(f"Processing download request for: {video_url}")
    result = fetch_tiktok_data(video_url)

    # ৩. রেসপন্স পাঠানো
    if result['success']:
        logger.info("Download success.")
        return jsonify(result)
    else:
        logger.error(f"Download failed: {result.get('error')}")
        return jsonify(result), 400

if __name__ == '__main__':
    # রেন্ডার বা লোকাল এনভায়রনমেন্টের জন্য পোর্ট সেটিংস
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    

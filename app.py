import os
import re
import logging
import itertools
import requests
from flask import Flask, render_template, request, jsonify

# Logging setup for Render logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__, template_folder='templates')

# API Key Configuration: Sequential Rotation
api_keys_list = [k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()]
key_cycle = itertools.cycle(api_keys_list)

def is_valid_tiktok_url(url):
    """Validate TikTok URLs using Regex"""
    pattern = r'^(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/.+'
    return bool(re.match(pattern, url))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    if not api_keys_list:
        return jsonify({'success': False, 'error': 'API keys not configured on server.'}), 500

    data = request.json
    video_url = data.get('url')

    # 1. URL Validation
    if not video_url or not is_valid_tiktok_url(video_url):
        return jsonify({'success': False, 'error': 'Invalid TikTok URL.'}), 400

    api_url = "https://tiktok-video-no-watermark2.p.rapidapi.com/"
    
    # 2. Sequential Key Rotation & Retry Logic
    # We try up to the number of keys we have in the list
    for _ in range(len(api_keys_list)):
        current_key = next(key_cycle)
        headers = {
            "x-rapidapi-host": "tiktok-video-no-watermark2.p.rapidapi.com",
            "x-rapidapi-key": current_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            response = requests.post(api_url, headers=headers, data={"url": video_url, "hd": "1"}, timeout=15)
            
            # If rate limited, log it and try next key
            if response.status_code == 429:
                logging.warning(f"API Key {current_key[:5]}... hit rate limit. Switching key.")
                continue
                
            if response.status_code != 200:
                logging.error(f"API returned status {response.status_code}")
                continue

            result = response.json()
            
            if result.get('code') == 0:
                d = result.get('data', {})
                # Successfully found video
                return jsonify({
                    'success': True,
                    'hd_url': d.get('hdplay') or d.get('play'),
                    'sd_url': d.get('play'),
                    'thumbnail': d.get('cover'),
                    'title': d.get('title') or "Untitled Video",
                    'author': d.get('author', {}).get('unique_id') or "Unknown",
                    'duration': d.get('duration') or 0
                })
            else:
                # Video not found, private, or other logic error
                return jsonify({'success': False, 'error': 'Video not found or is private.'}), 404
                
        except requests.exceptions.Timeout:
            logging.error("API Request timed out.")
            continue
        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            continue

    # If loop finishes without returning, all keys failed
    return jsonify({'success': False, 'error': 'All API keys are currently exhausted or server error.'}), 503

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
               

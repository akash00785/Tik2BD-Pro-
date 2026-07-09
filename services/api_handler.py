import requests
import logging
from config import key_manager, TIMEOUT

def fetch_tiktok_data(video_url):
    """
    TikTok ভিডিও বা ফটো মোডের ডেটা ফেচ করার জন্য মেইন ফাংশন।
    """
    api_url = "https://tiktok-video-no-watermark2.p.rapidapi.com/"
    
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
            response = requests.post(api_url, headers=headers, data={"url": video_url, "hd": "1"}, timeout=TIMEOUT)
            
            if response.status_code == 429:
                key_manager.mark_failed(key_obj['val'])
                continue

            if response.status_code != 200:
                continue

            result = response.json()

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

        except Exception as e:
            logging.error(f"Unexpected API Error: {str(e)}")
            continue

    return {'success': False, 'error': 'System busy, please try again.'}


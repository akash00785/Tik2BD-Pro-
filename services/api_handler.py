import requests
import logging
from config import key_manager, TIMEOUT

def fetch_tiktok_data(video_url):
    """
    TikTok ভিডিওর ডেটা ফেচ করার জন্য মেইন ফাংশন।
    এটি সফলভাবে ডেটা রিটার্ন করবে অথবা এরর হ্যান্ডেল করবে।
    """
    api_url = "https://tiktok-video-no-watermark2.p.rapidapi.com/"
    
    # প্রজেক্টের কনফিগারেশন অনুযায়ী কীগুলো লুপ করবে
    for _ in range(len(key_manager.keys)):
        key_obj = key_manager.get_active_key()
        
        # যদি কোনো কী না থাকে (সব শেষ হয়ে যায়)
        if not key_obj:
            logging.error("Critical: All API keys exhausted.")
            return {'success': False, 'error': 'Service temporarily unavailable. Please try later.'}

        headers = {
            "x-rapidapi-host": "tiktok-video-no-watermark2.p.rapidapi.com",
            "x-rapidapi-key": key_obj['val'],
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            # API Request
            response = requests.post(api_url, headers=headers, data={"url": video_url, "hd": "1"}, timeout=TIMEOUT)
            
            # রেট লিমিট হ্যান্ডলিং (429)
            if response.status_code == 429:
                key_manager.mark_failed(key_obj['val'])
                logging.warning(f"Rate limit hit for key: {key_obj['val'][:5]}... Switching.")
                continue

            # রেসপন্স চেক
            if response.status_code != 200:
                logging.error(f"API Error: Status {response.status_code}")
                continue

            result = response.json()

            # সাকসেস লজিক
            if result.get('code') == 0:
                d = result.get('data', {})
                return {
                    'success': True,
                    'hd_url': d.get('hdplay'),
                    'sd_url': d.get('play'),
                    'thumbnail': d.get('cover'),
                    'title': d.get('title') or "Untitled Video",
                    'author': d.get('author', {}).get('unique_id') or "Unknown",
                    'duration': d.get('duration') or 0
                }
            else:
                return {'success': False, 'error': 'Video not found or is private.'}

        except requests.exceptions.Timeout:
            logging.error("API request timed out.")
            continue
        except Exception as e:
            logging.error(f"Unexpected API Error: {str(e)}")
            continue

    return {'success': False, 'error': 'System busy, please try again.'}
              

"""
RapidAPI রেজাল্ট ক্যাশ — Upstash Redis-এর REST API ব্যবহার করে (hd_limiter.py
যেই একই ডেটাবেস ব্যবহার করে, আলাদা কোনো নতুন সিক্রেট/সার্ভিস লাগে না)।

কেন লাগে: প্রতিটা /download রিকোয়েস্টে RapidAPI-কে একটা কল যেতো, এমনকি
একই ভিডিও লিংক বহু ভিজিটর/বহুবার পেস্ট করলেও (ভাইরাল ভিডিওতে এটা খুব
সাধারণ)। এখন একই ভিডিও URL-এর রেজাল্ট কিছুক্ষণ (CACHE_TTL_SECONDS)
Redis-এ রাখা হয়, তাই ঐ সময়ের মধ্যে আবার সেই লিংক এলে RapidAPI-কে না
ডেকে ক্যাশ থেকেই উত্তর দেওয়া যায় — মাসিক কোটা বাঁচে।
"""

import json
import logging
import os

import requests

CACHE_TTL_SECONDS = 45 * 60  # ৪৫ মিনিট

UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL', '').rstrip('/')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')

_headers = {'Authorization': f'Bearer {UPSTASH_TOKEN}'}


def _configured():
    return bool(UPSTASH_URL and UPSTASH_TOKEN)


def _cmd(*parts):
    path = '/'.join(requests.utils.quote(str(p), safe='') for p in parts)
    resp = requests.get(f'{UPSTASH_URL}/{path}', headers=_headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get('result')


def _key(video_url):
    return f'rapidapi:cache:{video_url}'


def get_cached(video_url):
    """ক্যাশে থাকলে সেই dict রিটার্ন করে, না থাকলে/এরর হলে None।"""
    if not _configured():
        return None
    try:
        raw = _cmd('get', _key(video_url))
    except Exception as e:
        logging.warning(f"rapidapi_cache get failed (ignoring): {e}")
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def set_cached(video_url, result):
    """সফল রেজাল্টই ক্যাশ করা হয় — এরর/ব্যর্থ রেজাল্ট ক্যাশ করলে সাময়িক
    সমস্যাও ৪৫ মিনিট ধরে সবার জন্য দেখাতে থাকবে, তাই সেগুলো ক্যাশ করা হয় না।"""
    if not _configured() or not result or not result.get('success'):
        return
    try:
        _cmd('set', _key(video_url), json.dumps(result), 'EX', CACHE_TTL_SECONDS)
    except Exception as e:
        logging.warning(f"rapidapi_cache set failed (ignoring): {e}")

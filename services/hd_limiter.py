"""
প্রতি IP + ডিভাইস (কুকি) ভিত্তিক HD ডাউনলোড লিমিট + অ্যাড-গেট আনলক সিস্টেম।

Upstash Redis (ফ্রি টিয়ার) ব্যবহার করা হয়েছে — REST API দিয়ে, তাই আলাদা
কোনো Redis ক্লায়েন্ট প্যাকেজ ইন্সটল করার দরকার নেই, শুধু `requests`
যথেষ্ট। ডেটা Upstash-এর সার্ভারে থাকে বলে Render রিস্টার্ট/রিডিপ্লয়/
স্লিপ হলেও HD ডাউনলোড কাউন্ট মুছে যায় না — আগে SQLite ফাইলে রাখা হতো,
যেটা Render ফ্রি প্ল্যানের "ephemeral disk"-এর কারণে রিস্টার্টে মুছে
যাচ্ছিল, তাই সবার লিমিট বারবার ৫-এ রিসেট হয়ে যাচ্ছিল।

এই ফাইল কাজ করার জন্য দুইটা এনভায়রনমেন্ট ভ্যারিয়েবল লাগবে (Render-এর
Environment ট্যাবে যোগ করতে হবে):
  UPSTASH_REDIS_REST_URL
  UPSTASH_REDIS_REST_TOKEN
(upstash.com-এ ফ্রি ডেটাবেস তৈরি করলে "REST API" সেকশনে এই দুটো পাওয়া
যায়।)

লিমিট এখানে একটা "fixed window" হিসেবে কাজ করে (rolling window না) —
মানে কেউ প্রথম HD ডাউনলোড করার মুহূর্ত থেকে ২৪ ঘণ্টার একটা কাউন্টার শুরু
হয়, ২৪ ঘণ্টা পর Redis নিজে থেকেই কাউন্টার মুছে দেয় (TTL), তখন আবার নতুন
৫টা ফ্রি ডাউনলোড পাওয়া যায়।
"""

import os
import time
import secrets

import requests

from ads_config import FREE_HD_LIMIT, UNLOCK_GRANTS

WINDOW_SECONDS = 24 * 60 * 60
PENDING_TTL_SECONDS = 30 * 60  # অ্যাড ক্লিকের পর টোকেন কতক্ষণ বৈধ থাকবে

UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL', '').rstrip('/')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')

_headers = {'Authorization': f'Bearer {UPSTASH_TOKEN}'}


def _configured():
    return bool(UPSTASH_URL and UPSTASH_TOKEN)


def _cmd(*parts):
    """
    Upstash REST API-তে একটা Redis কমান্ড পাঠায়। parts-এর প্রতিটা অংশ
    URL-এ যোগ করার আগে quote করা হয় (কী-তে : বা / থাকলেও যেন ভেঙে না
    যায়)।
    """
    if not _configured():
        raise RuntimeError(
            'UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN সেট করা নেই। '
            'Render-এর Environment ট্যাবে এই দুটো ভ্যারিয়েবল যোগ করুন।'
        )
    path = '/'.join(requests.utils.quote(str(p), safe='') for p in parts)
    resp = requests.get(f'{UPSTASH_URL}/{path}', headers=_headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get('result')


def _key_usage(ip, device_id):
    # আগে key-টা ip+device_id দুটো মিলিয়ে বানানো হতো — কিন্তু মোবাইল
    # নেটওয়ার্কে (4G/wifi সুইচ, carrier NAT) একই ব্যবহারকারীর IP প্রায়ই
    # বদলে যায়, ফলে নতুন key তৈরি হয়ে যেতো এবং লিমিট ভুলভাবে ৫/৫-এ
    # "রিসেট" হয়ে যাচ্ছিল যদিও device (কুকি) একই ছিল। device_id-টাই
    # দীর্ঘস্থায়ী ও নির্ভরযোগ্য পরিচয়, তাই এখন শুধু device_id দিয়েই key।
    return f'hd:used:{device_id}'


def _key_grants(ip, device_id):
    return f'hd:grants:{device_id}'


def _key_pending(token):
    return f'hd:pending:{token}'


def init_db():
    """SQLite যুগের নাম রাখা হয়েছে backward-compat-এর জন্য — Upstash-এ
    আলাদা করে টেবিল/স্কিমা বানানোর দরকার নেই।"""
    return None


def get_status(ip, device_id):
    """বর্তমান অবস্থা রিটার্ন করে — লক আছে কিনা, কতক্ষণে রিসেট হবে ইত্যাদি।"""
    used_raw = _cmd('get', _key_usage(ip, device_id))
    used = int(used_raw) if used_raw else 0
    grants_raw = _cmd('get', _key_grants(ip, device_id))
    grants = int(grants_raw) if grants_raw else 0

    remaining_free = max(0, FREE_HD_LIMIT - used)
    locked = remaining_free <= 0 and grants <= 0

    resets_in_seconds = 0
    if used > 0:
        ttl = _cmd('ttl', _key_usage(ip, device_id))
        if isinstance(ttl, int) and ttl > 0:
            resets_in_seconds = ttl

    return {
        'locked': locked,
        'used': used,
        'limit': FREE_HD_LIMIT,
        'remaining_free': remaining_free,
        'available_grants': grants,
        'resets_in_seconds': resets_in_seconds,
    }


def try_consume(ip, device_id):
    """
    একটা HD ডাউনলোড অনুমোদিত কিনা চেক করে, অনুমোদিত হলে সাথে সাথেই
    হিসেবে যুক্ত করে। রিটার্ন করে (allowed: bool, status: dict)
    """
    usage_key = _key_usage(ip, device_id)
    used_raw = _cmd('get', usage_key)
    used = int(used_raw) if used_raw else 0

    if used < FREE_HD_LIMIT:
        new_used = _cmd('incr', usage_key)
        if new_used == 1:
            # এই IP+ডিভাইসের প্রথম ডাউনলোড — এখান থেকেই ২৪ ঘণ্টার
            # উইন্ডো শুরু হলো, TTL বসিয়ে দেওয়া হচ্ছে
            _cmd('expire', usage_key, WINDOW_SECONDS)
        return True, get_status(ip, device_id)

    grants_key = _key_grants(ip, device_id)
    grants_raw = _cmd('get', grants_key)
    grants = int(grants_raw) if grants_raw else 0
    if grants > 0:
        _cmd('decr', grants_key)
        _cmd('incr', usage_key)
        return True, get_status(ip, device_id)

    return False, get_status(ip, device_id)


def start_unlock(ip, device_id):
    """অ্যাড লিংকে ক্লিক করার মুহূর্তে একটা টোকেন ইস্যু করা হয়, যেটা দিয়ে
    পরে (নির্দিষ্ট অপেক্ষার পর) আনলক claim করা যাবে।"""
    now = time.time()
    token = secrets.token_urlsafe(16)
    value = f'{ip}|{device_id}|{now}'
    _cmd('set', _key_pending(token), value, 'EX', PENDING_TTL_SECONDS)
    return token


def claim_unlock(token, ip, device_id, wait_seconds):
    """অপেক্ষার সময় শেষ হলে টোকেনটা এক্সচেঞ্জ করে আনলক গ্র্যান্ট দেওয়া হয়।
    টোকেন একবারই ব্যবহার করা যাবে।"""
    now = time.time()
    pending_key = _key_pending(token)
    raw = _cmd('get', pending_key)
    if not raw:
        return False, 'invalid_token'

    try:
        row_ip, row_device_id, started_at_str = raw.split('|', 2)
        started_at = float(started_at_str)
    except (ValueError, AttributeError):
        _cmd('del', pending_key)
        return False, 'invalid_token'

    # IP মেলা বাধ্যতামূলক না — মোবাইল নেটওয়ার্কে অ্যাড দেখার সময়
    # (৩০ সেকেন্ড অপেক্ষা) IP বদলে যাওয়াটা স্বাভাবিক। device_id-টাই
    # (দীর্ঘস্থায়ী কুকি) মূল যাচাই।
    if row_device_id != device_id:
        return False, 'mismatch'

    _cmd('del', pending_key)

    if now - started_at < wait_seconds:
        return False, 'too_soon'

    grants_key = _key_grants(ip, device_id)
    _cmd('incrby', grants_key, UNLOCK_GRANTS)
    return True, None


init_db()

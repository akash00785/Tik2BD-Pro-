"""
প্রতি IP + ডিভাইস (কুকি) ভিত্তিক HD ডাউনলোড লিমিট + অ্যাড-গেট আনলক সিস্টেম।

SQLite ব্যবহার করা হয়েছে (আলাদা কোনো ডাটাবেস সার্ভার লাগবে না, বাড়তি
কোনো প্যাকেজ ইন্সটল করার দরকার নেই)। ফাইলটা রাখা হয় `data/limiter.db`-এ।

লক্ষ্য রাখুন: Render-এর ফ্রি প্ল্যানে ডিস্ক "ephemeral" — মানে নতুন
deploy/restart হলে এই ফাইল ও তার ভেতরের কাউন্ট মুছে যেতে পারে। এটা এই
ফিচারের জন্য বড় সমস্যা না (worst case কেউ deploy-এর ঠিক পরে বাড়তি
কয়েকটা ফ্রি ডাউনলোড পাবে), কিন্তু নিশ্চিত/persistent count রাখতে হলে
ভবিষ্যতে একটা persistent disk বা Postgres লাগবে।
"""

import os
import sqlite3
import time
import secrets
import threading

from ads_config import FREE_HD_LIMIT, UNLOCK_GRANTS

# Render-এ persistent disk যোগ করার পর তার মাউন্ট পাথ DATA_DIR এনভায়রনমেন্ট
# ভ্যারিয়েবলে বসিয়ে দিলে ডাটাবেস ফাইলটা সেই স্থায়ী ডিস্কে থাকবে, তাই
# সার্ভার রিস্টার্ট/রিডিপ্লয় হলেও HD ডাউনলোড কাউন্ট মুছে যাবে না। এই
# ভ্যারিয়েবল সেট না থাকলে আগের মতোই প্রজেক্ট ফোল্ডারের ভেতরের data/
# ফোল্ডারে থাকবে (Render ফ্রি প্ল্যানে এই ফোল্ডার রিস্টার্টে মুছে যায়)।
DB_DIR = os.environ.get(
    'DATA_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
)
DB_PATH = os.path.join(DB_DIR, 'limiter.db')

WINDOW_SECONDS = 24 * 60 * 60

_lock = threading.RLock()  # try_consume() থেকে get_status() কে ভেতরে ভেতরে
                            # কল করা হয়, তাই সাধারণ Lock দিলে একই থ্রেডে
                            # দ্বিতীয়বার lock নিতে গিয়ে deadlock হয়ে যেত।


def _get_conn():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    with _lock, _get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS hd_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                device_id TEXT NOT NULL,
                ts REAL NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS unlock_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                device_id TEXT NOT NULL,
                granted_at REAL NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_unlocks (
                token TEXT PRIMARY KEY,
                ip TEXT NOT NULL,
                device_id TEXT NOT NULL,
                started_at REAL NOT NULL
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_hd_downloads_key ON hd_downloads (ip, device_id, ts)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_unlock_grants_key ON unlock_grants (ip, device_id, used)')
        conn.commit()


def _usage_count(conn, ip, device_id, now):
    cur = conn.execute(
        'SELECT COUNT(*) FROM hd_downloads WHERE ip=? AND device_id=? AND ts > ?',
        (ip, device_id, now - WINDOW_SECONDS)
    )
    return cur.fetchone()[0]


def _available_grants(conn, ip, device_id):
    cur = conn.execute(
        'SELECT COUNT(*) FROM unlock_grants WHERE ip=? AND device_id=? AND used=0',
        (ip, device_id)
    )
    return cur.fetchone()[0]


def _oldest_download_ts(conn, ip, device_id, now):
    cur = conn.execute(
        'SELECT MIN(ts) FROM hd_downloads WHERE ip=? AND device_id=? AND ts > ?',
        (ip, device_id, now - WINDOW_SECONDS)
    )
    row = cur.fetchone()
    return row[0]


def get_status(ip, device_id):
    """বর্তমান অবস্থা রিটার্ন করে — লক আছে কিনা, কতক্ষণে রিসেট হবে ইত্যাদি।"""
    now = time.time()
    with _lock, _get_conn() as conn:
        used = _usage_count(conn, ip, device_id, now)
        grants = _available_grants(conn, ip, device_id)
        remaining_free = max(0, FREE_HD_LIMIT - used)
        locked = remaining_free <= 0 and grants <= 0

        resets_in_seconds = 0
        if locked:
            oldest = _oldest_download_ts(conn, ip, device_id, now)
            if oldest:
                resets_in_seconds = max(0, int(oldest + WINDOW_SECONDS - now))

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
    হিসেবে যুক্ত করে (atomic — একই সময়ে দুইটা রিকোয়েস্ট এসে race
    condition-এ ভুল করে দুইটাই পাস করে যাবে না)।
    রিটার্ন করে (allowed: bool, status: dict)
    """
    now = time.time()
    with _lock, _get_conn() as conn:
        used = _usage_count(conn, ip, device_id, now)

        if used < FREE_HD_LIMIT:
            conn.execute(
                'INSERT INTO hd_downloads (ip, device_id, ts) VALUES (?, ?, ?)',
                (ip, device_id, now)
            )
            conn.commit()
            return True, get_status(ip, device_id)

        cur = conn.execute(
            'SELECT id FROM unlock_grants WHERE ip=? AND device_id=? AND used=0 ORDER BY id LIMIT 1',
            (ip, device_id)
        )
        row = cur.fetchone()
        if row:
            conn.execute('UPDATE unlock_grants SET used=1 WHERE id=?', (row[0],))
            conn.execute(
                'INSERT INTO hd_downloads (ip, device_id, ts) VALUES (?, ?, ?)',
                (ip, device_id, now)
            )
            conn.commit()
            return True, get_status(ip, device_id)

        return False, get_status(ip, device_id)


def start_unlock(ip, device_id):
    """অ্যাড লিংকে ক্লিক করার মুহূর্তে একটা টোকেন ইস্যু করা হয়, যেটা দিয়ে
    পরে (নির্দিষ্ট অপেক্ষার পর) আনলক claim করা যাবে।"""
    now = time.time()
    token = secrets.token_urlsafe(16)
    with _lock, _get_conn() as conn:
        # পুরনো (৩০ মিনিটের বেশি আগের) pending token পরিষ্কার করা হচ্ছে
        conn.execute('DELETE FROM pending_unlocks WHERE started_at < ?', (now - 1800,))
        conn.execute(
            'INSERT INTO pending_unlocks (token, ip, device_id, started_at) VALUES (?, ?, ?, ?)',
            (token, ip, device_id, now)
        )
        conn.commit()
    return token


def claim_unlock(token, ip, device_id, wait_seconds):
    """অপেক্ষার সময় শেষ হলে টোকেনটা এক্সচেঞ্জ করে আনলক গ্র্যান্ট দেওয়া হয়।
    টোকেন একবারই ব্যবহার করা যাবে।"""
    now = time.time()
    with _lock, _get_conn() as conn:
        cur = conn.execute(
            'SELECT ip, device_id, started_at FROM pending_unlocks WHERE token=?',
            (token,)
        )
        row = cur.fetchone()
        if not row:
            return False, 'invalid_token'

        row_ip, row_device_id, started_at = row
        if row_ip != ip or row_device_id != device_id:
            return False, 'mismatch'

        conn.execute('DELETE FROM pending_unlocks WHERE token=?', (token,))

        if now - started_at < wait_seconds:
            conn.commit()
            return False, 'too_soon'

        for _ in range(UNLOCK_GRANTS):
            conn.execute(
                'INSERT INTO unlock_grants (ip, device_id, granted_at, used) VALUES (?, ?, ?, 0)',
                (ip, device_id, now)
            )
        conn.commit()
        return True, None


init_db()

import os
import time
import logging

# কনফিগারেশন সেটিংস
class KeyManager:
    def __init__(self, keys_str):
        # API_KEYS এনভায়রনমেন্ট ভেরিয়েবল থেকে লিস্ট তৈরি
        # উদাহরণ: API_KEYS=keyA,keyB,keyC
        self.keys = [{'val': k.strip(), 'active': True, 'failed_at': 0}
                     for k in keys_str.split(",") if k.strip()]

        # RapidAPI free plan মাসে রিনিউ হয়।
        # ২৪ ঘণ্টা পর ব্যর্থ key আবার চেষ্টা করা হবে —
        # রিনিউ হয়ে থাকলে কাজ করবে, না হলে আবার skip হবে।
        self.cooldown = 86400  # ২৪ ঘণ্টা (সেকেন্ডে)

    def get_active_key(self):
        """সক্রিয় key ফেরত দেয়। cooldown শেষ হলে key পুনরায় চালু হয়।"""
        now = time.time()
        for k in self.keys:
            # cooldown শেষ হলে key পুনরায় সক্রিয় করো
            if not k['active'] and (now - k['failed_at'] > self.cooldown):
                k['active'] = True
                logging.info(f"Key re-activated after cooldown: {k['val'][:8]}...")
            if k['active']:
                return k
        return None

    def mark_failed(self, key_val):
        """Rate limit (429) হলে key কে ২৪ ঘণ্টার জন্য নিষ্ক্রিয় করো।"""
        for k in self.keys:
            if k['val'] == key_val:
                k['active'] = False
                k['failed_at'] = time.time()
                remaining = [x for x in self.keys if x['active']]
                logging.warning(
                    f"Key exhausted: {key_val[:8]}... | "
                    f"Active keys remaining: {len(remaining)}"
                )

    def status(self):
        """সব key-এর অবস্থা লগে দেখায়।"""
        now = time.time()
        report = []
        for i, k in enumerate(self.keys):
            if k['active']:
                state = "active"
            else:
                hours_left = max(0, (self.cooldown - (now - k['failed_at'])) / 3600)
                state = f"cooldown ({hours_left:.1f}h left)"
            report.append(f"Key {i+1}: {k['val'][:8]}... -> {state}")
        return " | ".join(report)


# API_KEYS ইনিশিয়ালাইজেশন
api_keys_env = os.environ.get("API_KEYS", "")
key_manager = KeyManager(api_keys_env)

if key_manager.keys:
    logging.info(f"KeyManager loaded {len(key_manager.keys)} key(s).")
else:
    logging.critical("No API keys found! Set API_KEYS environment variable.")

# অন্যান্য কনফিগারেশন
TIMEOUT = 15

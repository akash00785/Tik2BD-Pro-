import os
import time
import logging


class KeyManager:
    def __init__(self, keys_str):
        self.keys = [{'val': k.strip(), 'active': True, 'failed_at': 0}
                     for k in keys_str.split(",") if k.strip()]
        self.cooldown = 86400  # ২৪ ঘণ্টা

    def get_active_key(self):
        now = time.time()
        for k in self.keys:
            if not k['active'] and (now - k['failed_at'] > self.cooldown):
                k['active'] = True
                logging.info(f"Key re-activated after cooldown: {k['val'][:8]}...")
            if k['active']:
                return k
        return None

    def mark_failed(self, key_val):
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


# API_KEYS env var থেকে লোড করা
api_keys_env = os.environ.get("API_KEYS", "")
key_manager = KeyManager(api_keys_env)

if key_manager.keys:
    logging.info(f"KeyManager loaded {len(key_manager.keys)} key(s).")
else:
    logging.warning("No API keys found. HD Download will be unavailable. Set API_KEYS env var for HD.")

TIMEOUT = 15

import os
import time
import logging

# কনফিগারেশন সেটিংস
class KeyManager:
    def __init__(self, keys_str):
        # API_KEYS এনভায়রনমেন্ট ভেরিয়েবল থেকে লিস্ট তৈরি
        self.keys = [{'val': k.strip(), 'active': True, 'failed_at': 0} 
                     for k in keys_str.split(",") if k.strip()]
        self.cooldown = 300 # ৫ মিনিট

    def get_active_key(self):
        now = time.time()
        for k in self.keys:
            if not k['active'] and (now - k['failed_at'] > self.cooldown):
                k['active'] = True
            if k['active']:
                return k
        return None

    def mark_failed(self, key_val):
        for k in self.keys:
            if k['val'] == key_val:
                k['active'] = False
                k['failed_at'] = time.time()
                logging.warning(f"Key exhausted: {key_val[:5]}...")

# API_KEYS ইনিশিয়ালাইজেশন
api_keys_env = os.environ.get("API_KEYS", "")
key_manager = KeyManager(api_keys_env)

# অন্যান্য কনফিগারেশন
TIMEOUT = 15


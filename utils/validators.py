import re

def is_valid_tiktok_url(url):
    """
    TikTok URL ভ্যালিডেশন।
    tiktok.com, vm.tiktok.com, vt.tiktok.com এবং m.tiktok.com সাপোর্ট করে।
    """
    if not url:
        return False

    pattern = r'^(https?://)?(www\.|m\.)?(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/.+'
    return bool(re.match(pattern, url))

import re

def is_valid_tiktok_url(url):
    """
    ইউজার ইনপুটটি টিকটক লিঙ্ক কি না তা যাচাই করে।
    এটি tiktok.com, vm.tiktok.com এবং vt.tiktok.com ফরম্যাট সাপোর্ট করে।
    """
    if not url:
        return False
    
    # রেগুলার এক্সপ্রেশন ব্যবহার করে লিঙ্ক ভ্যালিডেশন
    pattern = r'^(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/.+'
    
    return bool(re.match(pattern, url))
  

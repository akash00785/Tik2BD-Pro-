# Tik2BD Pro — TikTok Video Downloader

একটি পেশাদার TikTok ভিডিও ডাউনলোডার। Watermark ছাড়া HD মানের ভিডিও ও ফটো ডাউনলোড করুন।

## Features

- ✅ Watermark-মুক্ত ভিডিও ডাউনলোড
- ✅ HD ও SD কোয়ালিটি সাপোর্ট
- ✅ TikTok Photo/Slideshow সাপোর্ট
- ✅ একাধিক API Key rotation
- ✅ মোবাইল-বান্ধব ডিজাইন

## Stack

- **Backend:** Python + Flask
- **API:** RapidAPI — TikTok Video No Watermark
- **Server:** Gunicorn
- **Frontend:** Tailwind CSS + Vanilla JS

## Local Setup

```bash
# ১. রিপো ক্লোন করুন
git clone https://github.com/akash00785/Tik2BD-Pro-.git
cd Tik2BD-Pro-

# ২. ভার্চুয়াল এনভায়রনমেন্ট তৈরি করুন
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# ৩. Dependencies ইন্সটল করুন
pip install -r requirements.txt

# ৪. Environment variables সেট করুন
cp .env.example .env
# .env ফাইলে আপনার API_KEYS দিন

# ৫. রান করুন
python app.py
```

## Environment Variables

`.env` ফাইল তৈরি করুন (`.gitignore`-এ আছে, GitHub-এ যাবে না):

```
API_KEYS=your_rapidapi_key_1,your_rapidapi_key_2
PORT=5000
FLASK_DEBUG=false
```

## Deployment (Render)

1. Render.com-এ নতুন Web Service তৈরি করুন
2. এই GitHub রিপো কানেক্ট করুন
3. Environment variables-এ `API_KEYS` সেট করুন
4. `Procfile` অটোমেটিক detect হবে

## Developed By

**Akash Islam** | Powered by **SkyNet Digital AI**  
&copy; 2026 Tik2BD. All Rights Reserved.

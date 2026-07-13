# Tik2BD Pro

TikTok Video Downloader — No Watermark, HD Quality

## Features
- Normal Download (API key ছাড়া, yt-dlp powered)
- HD Download (RapidAPI key দিয়ে)
- Photo Slideshow download
- HD rate limiting (5 free/day per IP)

## Setup
```bash
pip install -r requirements.txt
python app.py
```

## Environment Variables
- `API_KEYS` — RapidAPI key(s), comma-separated (HD download এর জন্য)
- `PORT` — server port (default: 8000)

## Deploy on Render
Procfile দিয়ে সরাসরি deploy করুন।

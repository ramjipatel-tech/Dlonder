# DiskWala + TeraBox Telegram Bot (Koyeb starter)

This is a safe starter bot for authorized direct video-file URLs and Telegram video uploads.

## Supported now
- /start and /help
- Download authorized direct HTTPS video-file URLs (MP4/MOV/WebM/MKV/AVI)
- Receive a video uploaded to Telegram and send it back
- Reject localhost/private-network destinations and optionally restrict allowed domains
- Configurable maximum download size

## Not implemented
DiskWala and TeraBox share-page extraction is **not implemented**. The bot recognizes those links and explains that it needs an authorized direct file URL. It does not scrape share pages, remove ads, bypass login/OTP/CAPTCHA, defeat DRM, or evade platform download restrictions.

## Deploy on Koyeb
1. Create a Koyeb app from this GitHub repository.
2. Choose Dockerfile as the build method.
3. Create a secret environment variable named BOT_TOKEN with the token from @BotFather.
4. Add MAX_FILE_MB (for example 1000, depending on your instance resources).
5. Deploy as a worker/service. The bot uses Telegram long polling and does not need an inbound HTTP port.
6. Open the bot in Telegram and send /start.

## Run locally
Python 3.10+:
- Copy .env.example to .env
- Set BOT_TOKEN
- Install dependencies: pip install -r requirements.txt
- Run: python -m bot.main

## Environment
- BOT_TOKEN: required; keep it secret
- MAX_FILE_MB: download/upload size limit (default 1800 MB)
- DOWNLOAD_DIR: temporary download directory
- ALLOWED_HOSTS: optional comma-separated allowlist for direct URLs
- LOCAL_BOT_API_URL: optional URL for Telegram's official Local Bot API Server

## Large files
Koyeb instance disk, memory, execution limits and Telegram Bot API limits apply. Do not assume unlimited file sizes. For larger Telegram uploads, consider Telegram's official Local Bot API Server and a suitable cloud instance.

## Security
Never commit .env or your bot token. Use only videos you own or are authorized to download. Koyeb filesystem is temporary; files are deleted after processing.

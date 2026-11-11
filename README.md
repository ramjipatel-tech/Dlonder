# Dlonder — Telegram video helper

Telegram bot for authorized DiskWala and TeraBox share links, direct HTTPS video URLs, and Telegram video uploads.

## Share-link support
- **DiskWala:** uses the configurable third-party resolver at `DISKWALA_RESOLVER_URL`. Its availability and response format can change; it is not guaranteed.
- **TeraBox:** uses your own session cookie (`TERABOX_COOKIE`) with the service's share page and file-list flow. No login, OTP, CAPTCHA, DRM, paywall, or access-control bypass is implemented.
- TeraBox currently selects the first directly downloadable video file in the share. Folder traversal and multi-file selection are not implemented.

## Koyeb deployment
1. Deploy this GitHub repository from its Dockerfile as a **worker** (Telegram long polling).
2. Add `BOT_TOKEN` as a Koyeb Secret.
3. Keep `MAX_FILE_MB=45` for the standard hosted Telegram Bot API.
4. DiskWala resolver URL is configurable and has a default value in `.env.example`.
5. For TeraBox, add `TERABOX_COOKIE` as a Koyeb Secret using a session you own and are authorized to use. Never paste cookies into chat or commit them.
6. Deploy and test with a small video first.

## Limits and caveats
- The standard hosted Telegram Bot API has a 50 MB upload limit; this project defaults to 45 MB for headroom. Larger uploads require a separately hosted Telegram Local Bot API server and suitable cloud compute/storage.
- Koyeb ephemeral disk, memory, bandwidth and instance limits apply. This is not unlimited large-file hosting.
- The DiskWala resolver is third-party and may be unavailable or change. Code inspection is not proof that it currently resolves your sample link.
- TeraBox can reject expired cookies, unavailable shares, or unsupported files.
- Only download files you own or have permission to access.

## Run locally
```bash
cp .env.example .env
# Set BOT_TOKEN; optionally set TERABOX_COOKIE
pip install -r requirements.txt
python -m bot.main
``

## Environment
- `BOT_TOKEN` — required
- `MAX_FILE_MB` — default 45
- `DOWNLOAD_DIR` — default /tmp/downloads
- `DISKWALA_RESOLVER_URL` — default resolver endpoint
- `TERABOX_COOKIE` — optional own authorized session cookie
- `ALLOWED_HOSTS` — optional direct-download host allowlist
- `LOCAL_BOT_API_URL` — optional Local Bot API base URL

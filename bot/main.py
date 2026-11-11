import logging
from pathlib import Path
from urllib.parse import urlparse

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from .config import BOT_TOKEN, LOCAL_BOT_API_URL, MAX_FILE_MB, DOWNLOAD_DIR, ALLOWED_HOSTS
from .downloader import validate_url, download_direct_video

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
log = logging.getLogger("dlonder-bot")
MAX_BYTES = MAX_FILE_MB * 1024 * 1024

def platform_name(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "diskwala" in host:
        return "DiskWala"
    if "terabox" in host or "1024tera" in host:
        return "TeraBox"
    return "Direct video URL"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Dlonder!\n\n"
        "Send an authorized direct HTTPS video-file URL or upload a video here.\n"
        "DiskWala/TeraBox share-page extraction is not enabled in this starter. "
        "Use the platform's official download/export option and send a direct file URL.\n\n"
        "/help for instructions."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Send a direct HTTPS MP4/MOV/WebM/MKV/AVI URL or upload a video file.\n"
        f"Configured limit: {MAX_FILE_MB} MB.\n"
        "Share-page extraction, ad removal, login/OTP/CAPTCHA bypass and DRM circumvention are not supported."
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    urls = [part for part in text.split() if part.startswith("https://")]
    if not urls:
        return
    url = urls[0]
    platform = platform_name(url)
    if platform in ("DiskWala", "TeraBox"):
        await update.message.reply_text(
            f"{platform} link detected. This version does not extract media from share pages. "
            "Please use the official download/export option and provide an authorized direct HTTPS video URL."
        )
        return
    status = None
    path = None
    try:
        safe_url = validate_url(url, ALLOWED_HOSTS)
        status = await update.message.reply_text("⏳ Downloading direct video…")
        path = await download_direct_video(safe_url, DOWNLOAD_DIR, MAX_BYTES)
        await status.edit_text("⬆️ Download complete. Sending to Telegram…")
        await update.message.chat.send_action(ChatAction.UPLOAD_VIDEO)
        with path.open("rb") as f:
            await update.message.reply_video(video=f, caption=f"✅ {path.name}", supports_streaming=True,
                read_timeout=900, write_timeout=900, connect_timeout=60, pool_timeout=60)
        await status.delete()
    except Exception as exc:
        log.exception("URL processing failed")
        await update.message.reply_text(f"❌ Could not process URL: {exc}")
    finally:
        if path:
            path.unlink(missing_ok=True)

async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    media = msg.video or msg.document
    if not media:
        return
    name = getattr(media, "file_name", None) or "uploaded_video.mp4"
    if getattr(media, "file_size", 0) and media.file_size > MAX_BYTES:
        await msg.reply_text(f"File exceeds configured limit ({MAX_FILE_MB} MB).")
        return
    suffix = Path(name).suffix.lower()
    if suffix and suffix not in {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"}:
        await msg.reply_text("Please upload a supported video file.")
        return
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = DOWNLOAD_DIR / f"{msg.from_user.id}_{media.file_unique_id}_{Path(name).name}"
    status = await msg.reply_text("⏳ Receiving video…")
    try:
        tg_file = await context.bot.get_file(media.file_id)
        await tg_file.download_to_drive(custom_path=target)
        with target.open("rb") as f:
            await msg.reply_video(video=f, caption="✅ Video received.", supports_streaming=True)
        await status.delete()
    except Exception as exc:
        log.exception("Telegram upload processing failed")
        await msg.reply_text(f"❌ Upload failed: {exc}")
    finally:
        target.unlink(missing_ok=True)

def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing. Add it as a secret environment variable.")
    builder = Application.builder().token(BOT_TOKEN)
    if LOCAL_BOT_API_URL:
        builder = builder.base_url(f"{LOCAL_BOT_API_URL}/bot").base_file_url(f"{LOCAL_BOT_API_URL}/file/bot")
    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_upload))
    log.info("Dlonder bot starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

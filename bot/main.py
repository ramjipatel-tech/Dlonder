import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from .config import BOT_TOKEN, LOCAL_BOT_API_URL, MAX_FILE_MB, DOWNLOAD_DIR, ALLOWED_HOSTS
from .downloader import validate_url, download_direct_video
from .providers import provider_for, resolve_share

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
log = logging.getLogger("dlonder-bot")
MAX_BYTES = MAX_FILE_MB * 1024 * 1024
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Dlonder!\n\n"
        "Send a DiskWala or TeraBox share link, an authorized direct HTTPS video URL, or upload a video.\n"
        "DiskWala uses a third-party resolver. TeraBox requires your own authorized session cookie.\n\n/help for details."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Send a DiskWala/TeraBox share link or direct HTTPS video URL.\n"
        f"Current upload limit: {MAX_FILE_MB} MB.\n"
        "TeraBox requires TERABOX_COOKIE in environment secrets / Config Vars. Never share cookies or bot tokens in chat.\n"
        "Only download files you own or are authorized to access."
    )


async def _safe_edit(status_msg, text: str):
    if not status_msg:
        return
    try:
        await status_msg.edit_text(text)
    except Exception:
        pass


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    match = URL_RE.search(text)
    if not match:
        return
    url = match.group(0).rstrip(".,)]}")
    status = None
    path = None
    try:
        headers = None
        name = "video"
        provider = provider_for(url)
        if provider:
            status = await update.message.reply_text(f"🔎 Resolving {provider.title()} share link…")
            result = await resolve_share(url)
            name = result["name"]
            if result.get("size") and result["size"] > MAX_BYTES:
                raise ValueError(f"Video is larger than this bot's configured {MAX_FILE_MB} MB limit.")
            safe_url = validate_url(result["url"], ALLOWED_HOSTS)
            headers = result.get("headers")
            await _safe_edit(status, f"⏬ Downloading {name}…")
        else:
            safe_url = validate_url(url, ALLOWED_HOSTS)
            status = await update.message.reply_text("⏬ Downloading direct video…")
        path = await download_direct_video(
            safe_url,
            DOWNLOAD_DIR,
            MAX_BYTES,
            headers=headers,
            suggested_name=name if provider else None,
        )
        await _safe_edit(status, "⬆️ Download complete. Sending to Telegram…")
        await update.message.chat.send_action(ChatAction.UPLOAD_VIDEO)
        with path.open("rb") as f:
            await update.message.reply_video(
                video=f,
                filename=name if provider else path.name,
                caption=f"✅ {name if provider else path.name}",
                supports_streaming=True,
                read_timeout=900,
                write_timeout=900,
                connect_timeout=60,
                pool_timeout=60,
            )
        try:
            await status.delete()
        except Exception:
            pass
    except Exception as exc:
        log.exception("URL processing failed")
        if status:
            try:
                await status.edit_text(f"❌ Could not process link: {exc}")
            except Exception:
                await update.message.reply_text(f"❌ Could not process link: {exc}")
        else:
            await update.message.reply_text(f"❌ Could not process link: {exc}")
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

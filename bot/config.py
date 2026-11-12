import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
LOCAL_BOT_API_URL = os.getenv("LOCAL_BOT_API_URL", "").strip().rstrip("/")
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "2000" if LOCAL_BOT_API_URL else "45"))
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR") or (Path(tempfile.gettempdir()) / "dlonder_downloads"))
ALLOWED_HOSTS = {h.strip().lower() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()}

DISKWALA_RESOLVER_URL = os.getenv("DISKWALA_RESOLVER_URL", "https://diskwala-dl-six.vercel.app/api/scrap").strip()
TERABOX_COOKIE = os.getenv("TERABOX_COOKIE", "").strip()

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
LOCAL_BOT_API_URL = os.getenv("LOCAL_BOT_API_URL", "").strip()
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "1000"))
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/tmp/downloads"))
ALLOWED_HOSTS = {h.strip().lower() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()}

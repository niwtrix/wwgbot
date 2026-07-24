import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip()}
PROXY_URL = (
    os.getenv("PROXY_URL", "").strip()
    # PythonAnywhere's free tier injects these automatically for its outbound
    # allowlist proxy — fall back to them so no manual proxy address is needed.
    or os.getenv("https_proxy", "").strip()
    or os.getenv("HTTPS_PROXY", "").strip()
    or os.getenv("http_proxy", "").strip()
    or os.getenv("HTTP_PROXY", "").strip()
) or None
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()

DB_PATH = Path("/data/wwgang.sqlite3") if os.getenv("AMVERA") else BASE_DIR / "data" / "wwgang.sqlite3"

_database_url = os.getenv("DATABASE_URL", "").strip()
if _database_url:
    # Render/Neon/Supabase hand out plain postgres:// or postgresql:// URLs;
    # SQLAlchemy's async engine needs an explicit async-capable driver.
    if _database_url.startswith("postgres://"):
        _database_url = "postgresql://" + _database_url[len("postgres://") :]
    if _database_url.startswith("postgresql://"):
        _database_url = _database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    DB_URL = _database_url
else:
    DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

CARDS_DIR = BASE_DIR / "assets" / "cards"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")
if not OWNER_IDS:
    raise RuntimeError("OWNER_IDS is not set in .env")

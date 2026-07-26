import os

from app.config import BASE_DIR  # reuses the same .env already loaded by app.config

ADMIN_PANEL_PASSWORD = os.getenv("ADMIN_PANEL_PASSWORD", "")
ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", "")
ADMIN_PANEL_PORT = int(os.getenv("ADMIN_PANEL_PORT", "8811"))

if not ADMIN_PANEL_PASSWORD:
    raise RuntimeError("ADMIN_PANEL_PASSWORD is not set in .env")
if not ADMIN_SESSION_SECRET:
    raise RuntimeError("ADMIN_SESSION_SECRET is not set in .env")

TEMPLATES_DIR = BASE_DIR / "admin_web" / "templates"
STATIC_DIR = BASE_DIR / "admin_web" / "static"

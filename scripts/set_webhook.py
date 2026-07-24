"""One-off helper: registers the Telegram webhook after a Render deploy.

Usage:
    python scripts/set_webhook.py https://<app>.onrender.com

Reads BOT_TOKEN and WEBHOOK_SECRET from .env (or the environment).
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BOT_TOKEN, WEBHOOK_SECRET  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/set_webhook.py https://<app>.onrender.com")
        raise SystemExit(1)

    if not WEBHOOK_SECRET:
        raise SystemExit("WEBHOOK_SECRET is not set in .env")

    base_url = sys.argv[1].rstrip("/")
    payload = json.dumps(
        {"url": f"{base_url}/webhook", "secret_token": WEBHOOK_SECRET}
    ).encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(resp.read().decode())


if __name__ == "__main__":
    main()

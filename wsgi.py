import asyncio
import logging

from aiogram.types import Update
from flask import Flask, abort, request

from app.bot_setup import create_bot_and_dispatcher, set_bot_commands
from app.config import WEBHOOK_SECRET
from app.db.engine import init_db

logging.basicConfig(level=logging.INFO)

if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is not set — required for webhook mode")

asyncio.run(init_db())

bot, dp = create_bot_and_dispatcher()
asyncio.run(set_bot_commands(bot))

app = Flask(__name__)


@app.post("/webhook")
def telegram_webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        abort(403)

    update = Update.model_validate(request.get_json(force=True))
    asyncio.run(dp.feed_update(bot, update))
    return "OK"


@app.get("/")
def health():
    return "WWGang Cards bot is running."


application = app  # PythonAnywhere's WSGI convention expects this name

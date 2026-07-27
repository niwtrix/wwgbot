import asyncio
import logging

from aiogram import Bot

from app.bot_setup import create_bot_and_dispatcher, set_bot_commands
from app.config import PROXY_URL
from app.db.engine import init_db
from app.services.bonus_reminders import bonus_reminder_loop
from app.services.health_report import health_report_loop

KEEP_WARM_INTERVAL_SECONDS = 15


async def keep_warm(bot: Bot) -> None:
    """Periodically ping Telegram so the proxy tunnel's connection never goes idle
    long enough to be torn down (avoids a slow reconnect on the next real request)."""
    while True:
        try:
            await bot.get_me()
        except Exception:
            logging.warning("keep-warm ping failed", exc_info=True)
        await asyncio.sleep(KEEP_WARM_INTERVAL_SECONDS)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    await init_db()

    bot, dp = create_bot_and_dispatcher()

    await set_bot_commands(bot)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        logging.warning("Could not delete webhook on startup", exc_info=True)

    if PROXY_URL:
        asyncio.create_task(keep_warm(bot))
    asyncio.create_task(health_report_loop(bot))
    asyncio.create_task(bonus_reminder_loop(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

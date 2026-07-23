import asyncio
import logging

from app.bot_setup import create_bot_and_dispatcher, set_bot_commands
from app.db.engine import init_db


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    await init_db()

    bot, dp = create_bot_and_dispatcher()

    await set_bot_commands(bot)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        logging.warning("Could not delete webhook on startup", exc_info=True)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

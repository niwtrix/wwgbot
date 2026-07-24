from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from app.config import BOT_TOKEN, OWNER_IDS, PROXY_URL
from app.handlers import admin, user
from app.middlewares.db import DbSessionMiddleware
from app.middlewares.timing import TimingMiddleware

USER_COMMANDS = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="card", description="Получить карточку"),
    BotCommand(command="cases", description="Кейсы за токены"),
    BotCommand(command="profile", description="Мой профиль"),
    BotCommand(command="mycards", description="Мои карточки"),
    BotCommand(command="top", description="Топ игроков"),
    BotCommand(command="help", description="Помощь"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="admin", description="Панель администратора"),
    BotCommand(command="adminhelp", description="Справка для админов"),
    BotCommand(command="testcard", description="Показать тестовую карточку"),
    BotCommand(command="getemojiid", description="Получить ID премиум-эмодзи"),
    BotCommand(command="cancel", description="Отменить текущий ввод"),
]


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    dp.message.middleware(TimingMiddleware())
    dp.callback_query.middleware(TimingMiddleware())

    dp.include_router(admin.router)
    dp.include_router(user.router)

    return bot, dp


async def set_bot_commands(bot: Bot) -> None:
    import logging

    try:
        await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    except Exception:
        logging.warning("Could not set default commands", exc_info=True)

    for owner_id in OWNER_IDS:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=owner_id))
        except Exception:
            logging.warning("Could not set admin commands scope for %s", owner_id)

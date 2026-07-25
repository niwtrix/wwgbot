import asyncio
import logging
import time

from aiogram import Bot
from sqlalchemy import func, select

from app.config import OWNER_IDS
from app.db.engine import async_session
from app.db.models import User, UserCard
from app.db.settings_repo import get_setting, get_setting_int
from app.services.monitoring import average_duration_ms, sample_count

CHECK_INTERVAL_SECONDS = 30  # how often we re-check settings while idle


async def build_status_report(bot: Bot) -> str:
    ping_start = time.monotonic()
    try:
        await bot.get_me()
        ping_text = f"{(time.monotonic() - ping_start) * 1000:.0f} мс"
    except Exception:
        ping_text = "не отвечает ⚠️"

    async with async_session() as session:
        user_count = (await session.execute(select(func.count(User.id)))).scalar_one()
        total_pulls = (
            await session.execute(select(func.coalesce(func.sum(UserCard.count), 0)))
        ).scalar_one()
        total_tokens = (
            await session.execute(select(func.coalesce(func.sum(User.tokens), 0)))
        ).scalar_one()

    avg = average_duration_ms()
    avg_text = f"{avg:.0f} мс (по {sample_count()} последним)" if avg is not None else "нет данных ещё"

    return (
        "📊 <b>Статус бота</b>\n\n"
        f"🏓 Пинг Telegram: {ping_text}\n"
        f"⏱ Среднее время ответа: {avg_text}\n"
        f"👥 Пользователей бота: {user_count}\n"
        f"🃏 Карточек выдано всего: {total_pulls}\n"
        f"🪙 Токенов у всех на руках: {total_tokens}"
    )


async def health_report_loop(bot: Bot) -> None:
    last_sent = time.monotonic()
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            async with async_session() as session:
                enabled = (await get_setting(session, "health_report_enabled")) == "1"
                interval_minutes = await get_setting_int(session, "health_report_interval_minutes")
            if not enabled:
                continue
            if time.monotonic() - last_sent < interval_minutes * 60:
                continue

            last_sent = time.monotonic()
            text = await build_status_report(bot)
            for owner_id in OWNER_IDS:
                try:
                    await bot.send_message(owner_id, text, parse_mode="HTML")
                except Exception:
                    logging.warning("failed to send health report to %s", owner_id, exc_info=True)
        except Exception:
            logging.warning("health report loop iteration failed", exc_info=True)

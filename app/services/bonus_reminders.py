import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session
from app.db.models import User
from app.db.settings_repo import get_setting, get_setting_int, set_setting
from app.services.format import tg_emoji

CHECK_INTERVAL_SECONDS = 600

REMINDER_A_FALLBACK_EMOJI = "⏰"
REMINDER_B_FALLBACK_EMOJI = "🔥"


async def _build_text(session: AsyncSession, kind: str) -> str:
    if kind == "a":
        emoji_id = await get_setting(session, "reminder_a_emoji_id")
        body = await get_setting(session, "reminder_a_text")
        fallback = REMINDER_A_FALLBACK_EMOJI
    else:
        emoji_id = await get_setting(session, "reminder_b_emoji_id")
        body = await get_setting(session, "reminder_b_text")
        fallback = REMINDER_B_FALLBACK_EMOJI

    emoji = tg_emoji(fallback, emoji_id.strip() or None)
    return f"{emoji} <b>{body}</b>\n/bonus"


async def _candidates_a(session: AsyncSession) -> list[User]:
    now = datetime.now(timezone.utc)
    today_str = now.date().isoformat()
    yesterday_str = (now.date() - timedelta(days=1)).isoformat()

    result = await session.execute(
        select(User).where(
            or_(User.last_bonus_at.is_(None), func.date(User.last_bonus_at) != today_str),
            or_(func.date(User.last_pull_at) == yesterday_str, func.date(User.last_bonus_at) == yesterday_str),
        )
    )
    return list(result.scalars().all())


async def _candidates_b(session: AsyncSession, min_streak: int) -> list[User]:
    now = datetime.now(timezone.utc)
    today_str = now.date().isoformat()

    result = await session.execute(
        select(User).where(
            or_(User.last_bonus_at.is_(None), func.date(User.last_bonus_at) != today_str),
            User.daily_streak > min_streak,
        )
    )
    return list(result.scalars().all())


async def _send_batch(bot: Bot, text: str, users: list[User]) -> tuple[int, int]:
    sent = failed = 0
    for user in users:
        try:
            await bot.send_message(user.id, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    return sent, failed


async def send_preview(bot: Bot, session: AsyncSession, kind: str, username: str) -> str:
    username = username.strip().lstrip("@")
    result = await session.execute(select(User).where(func.lower(User.username) == username.lower()))
    user = result.scalar_one_or_none()
    if user is None:
        return f"Не нашёл пользователя @{username}."

    text = await _build_text(session, kind)
    try:
        await bot.send_message(user.id, text, parse_mode="HTML")
    except Exception as e:
        return f"Не удалось отправить: {e}"
    return f"Превью отправлено @{username}."


async def _check_reminder_a(bot: Bot) -> None:
    async with async_session() as session:
        if await get_setting(session, "reminder_a_enabled") != "1":
            return

        hour = await get_setting_int(session, "reminder_a_hour_utc")
        now = datetime.now(timezone.utc)
        if now.hour < hour:
            return

        today_str = now.date().isoformat()
        if await get_setting(session, "reminder_a_last_sent_date") == today_str:
            return

        candidates = await _candidates_a(session)
        if candidates:
            text = await _build_text(session, "a")
            sent, failed = await _send_batch(bot, text, candidates)
            logging.info("reminder A sent: %s ok, %s failed", sent, failed)

        await set_setting(session, "reminder_a_last_sent_date", today_str)


async def _check_reminder_b(bot: Bot) -> None:
    async with async_session() as session:
        if await get_setting(session, "reminder_b_enabled") != "1":
            return

        start_hour = await get_setting_int(session, "reminder_b_window_start_hour_utc")
        end_hour = await get_setting_int(session, "reminder_b_window_end_hour_utc")
        now = datetime.now(timezone.utc)
        if not (start_hour <= now.hour < end_hour):
            return

        today_str = now.date().isoformat()
        if await get_setting(session, "reminder_b_last_sent_date") == today_str:
            return

        window_start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        window_end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        remaining_seconds = max((window_end - now).total_seconds(), CHECK_INTERVAL_SECONDS)
        fire_probability = CHECK_INTERVAL_SECONDS / remaining_seconds
        if now < window_start or random.random() > fire_probability:
            return

        min_streak = await get_setting_int(session, "reminder_b_min_streak")
        candidates = await _candidates_b(session, min_streak)
        if candidates:
            text = await _build_text(session, "b")
            sent, failed = await _send_batch(bot, text, candidates)
            logging.info("reminder B sent: %s ok, %s failed", sent, failed)

        await set_setting(session, "reminder_b_last_sent_date", today_str)


async def bonus_reminder_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            await _check_reminder_a(bot)
        except Exception:
            logging.warning("reminder A check failed", exc_info=True)
        try:
            await _check_reminder_b(bot)
        except Exception:
            logging.warning("reminder B check failed", exc_info=True)

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CARDS_DIR
from app.db.models import Card
from app.keyboards.user import card_links_kb
from app.services.format import card_caption

SEND_RETRIES = 4
SEND_RETRY_DELAY_SECONDS = 1
UPLOAD_REQUEST_TIMEOUT_SECONDS = 12


async def _send_with_retry(coro_factory):
    last_error: Exception | None = None
    for attempt in range(1, SEND_RETRIES + 1):
        try:
            return await coro_factory()
        except TelegramNetworkError as e:
            last_error = e
            logging.warning("send attempt %s/%s failed: %s", attempt, SEND_RETRIES, e)
            if attempt < SEND_RETRIES:
                await asyncio.sleep(SEND_RETRY_DELAY_SECONDS)
    raise last_error


async def send_card(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    card: Card,
    *,
    extra_caption: str = "",
    reply_markup=None,
) -> Message:
    caption = card_caption(card, extra=extra_caption)
    kb = reply_markup if reply_markup is not None else card_links_kb(card)

    if card.tg_file_id:
        photo = card.tg_file_id
    elif card.photo_file:
        photo = FSInputFile(CARDS_DIR / card.photo_file)
    else:
        photo = None

    if photo is not None:
        message = await _send_with_retry(
            lambda: bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
                request_timeout=UPLOAD_REQUEST_TIMEOUT_SECONDS,
            )
        )
        if not card.tg_file_id and message.photo:
            card.tg_file_id = message.photo[-1].file_id
            await session.commit()
        return message

    return await _send_with_retry(
        lambda: bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
            reply_markup=kb,
            request_timeout=UPLOAD_REQUEST_TIMEOUT_SECONDS,
        )
    )

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.cards_repo import list_active_cards
from app.db.models import Card, User, UserCard
from app.db.settings_repo import get_setting_int
from app.keyboards.user import mycards_kb
from app.services.card_sender import send_card
from app.services.collection import pull_card
from app.services.users import get_or_create_user, seconds_until_ready

router = Router(name="user")

MYCARDS_PAGE_SIZE = 10


def fmt_seconds(total: int) -> str:
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ч {m} мин"
    if m:
        return f"{m} мин {s} сек"
    return f"{s} сек"


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    await get_or_create_user(session, message.from_user)
    await message.answer(
        "🎴 <b>WWGang Cards</b>\n\n"
        "Собирай карточки участников WWGang!\n\n"
        "/card — получить случайную карточку (по кулдауну)\n"
        "/profile — твой профиль и коллекция\n"
        "/mycards — список собранных карточек\n"
        "/top — таблица лидеров по токенам\n"
        "/help — помощь",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "🎴 <b>WWGang Cards — помощь</b>\n\n"
        "/card — получить случайную карточку участника WWGang (есть кулдаун между попытками)\n"
        "/profile — твои токены, прогресс коллекции и статус кулдауна\n"
        "/mycards — список всех твоих карточек с редкостью и количеством копий\n"
        "/top — топ игроков по токенам\n\n"
        "Токены начисляются за каждую карточку (больше — за редкие) и за дубликаты. "
        "Работает и в группе, и в личных сообщениях.",
        parse_mode="HTML",
    )


@router.message(Command("card", "wwg", "pull"))
async def cmd_card(message: Message, session: AsyncSession, bot: Bot) -> None:
    user = await get_or_create_user(session, message.from_user)

    cooldown_minutes = await get_setting_int(session, "cooldown_minutes")
    remaining = seconds_until_ready(user, cooldown_minutes)
    if remaining > 0:
        await message.answer(f"⏳ Следующую карточку можно будет получить через: {fmt_seconds(remaining)}")
        return

    result = await pull_card(session, user)
    if result is None:
        await message.answer("Пока в пуле нет ни одной карточки — загляните позже 🙏")
        return

    dup_note = ""
    if result.is_duplicate:
        dup_note = f"🔁 Дубликат (копия №{result.copies_owned})\n💰 Токены: +{result.tokens_awarded} (с бонусом за дубль)"
    else:
        dup_note = f"✨ Новая карточка в коллекции!\n💰 Токены: +{result.tokens_awarded}"

    await send_card(bot, message.chat.id, session, result.card, extra_caption=dup_note)


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(session, message.from_user)

    total_cards = len(await list_active_cards(session))

    result = await session.execute(
        select(func.count()).select_from(UserCard).where(UserCard.user_id == user.id)
    )
    unique_owned = result.scalar_one()

    result = await session.execute(
        select(func.coalesce(func.sum(UserCard.count), 0)).where(UserCard.user_id == user.id)
    )
    total_pulls = result.scalar_one()

    cooldown_minutes = await get_setting_int(session, "cooldown_minutes")
    remaining = seconds_until_ready(user, cooldown_minutes)
    cooldown_line = "✅ можно тянуть карту прямо сейчас" if remaining == 0 else f"⏳ через {fmt_seconds(remaining)}"

    await message.answer(
        f"👤 <b>Профиль {message.from_user.full_name}</b>\n\n"
        f"💰 Токены: {user.tokens}\n"
        f"🎴 Собрано уникальных: {unique_owned}/{total_cards}\n"
        f"📦 Всего карточек получено: {total_pulls}\n"
        f"🕒 Следующая карта: {cooldown_line}",
        parse_mode="HTML",
    )


async def _mycards_page_text(session: AsyncSession, user_id: int, page: int) -> tuple[str, int]:
    result = await session.execute(
        select(UserCard)
        .where(UserCard.user_id == user_id)
        .options(selectinload(UserCard.card).selectinload(Card.rarity))
        .join(Card)
        .order_by(Card.name)
    )
    owned = list(result.scalars().all())

    if not owned:
        return "У тебя пока нет карточек. Испытай удачу: /card", 1

    total_pages = (len(owned) + MYCARDS_PAGE_SIZE - 1) // MYCARDS_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = owned[page * MYCARDS_PAGE_SIZE : (page + 1) * MYCARDS_PAGE_SIZE]

    lines = [f"🎴 <b>Твои карточки</b> ({len(owned)} уник.)\n"]
    for uc in chunk:
        card = uc.card
        emoji = card.rarity.emoji_fallback
        copies = f" ×{uc.count}" if uc.count > 1 else ""
        lines.append(f"{emoji} {card.name} — {card.rarity.name}{copies}")

    return "\n".join(lines), total_pages


@router.message(Command("mycards"))
async def cmd_mycards(message: Message, session: AsyncSession) -> None:
    text, total_pages = await _mycards_page_text(session, message.from_user.id, 0)
    kb = mycards_kb(0, total_pages) if total_pages > 1 else None
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("mycards:"))
async def cb_mycards_page(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[1])
    text, total_pages = await _mycards_page_text(session, callback.from_user.id, page)
    kb = mycards_kb(page, total_pages) if total_pages > 1 else None
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(Command("top"))
async def cmd_top(message: Message, session: AsyncSession) -> None:
    result = await session.execute(
        select(User).order_by(User.tokens.desc()).limit(10)
    )
    top_users = list(result.scalars().all())

    if not top_users:
        await message.answer("Пока никто не собрал ни одного токена.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Топ по токенам</b>\n"]
    for i, u in enumerate(top_users):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        name = u.full_name or (f"@{u.username}" if u.username else str(u.id))
        lines.append(f"{prefix} {name} — {u.tokens} 💰")

    await message.answer("\n".join(lines), parse_mode="HTML")

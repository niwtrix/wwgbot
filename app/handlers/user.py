import contextlib

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.cards_repo import list_active_cards
from app.db.cases_repo import get_case, list_active_cases
from app.db.models import Card, User, UserCard
from app.db.settings_repo import get_setting, get_setting_int
from app.keyboards.user import buy_roll_kb, cases_list_kb, mycards_gallery_kb, mycards_kb, profile_kb, top_kb
from app.services.card_sender import send_card
from app.services.collection import buy_extra_roll, open_case, pull_card
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
async def cmd_start(message: Message, session: AsyncSession, bot: Bot) -> None:
    args = (message.text or "").split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else ""

    is_new = await session.get(User, message.from_user.id) is None
    user = await get_or_create_user(session, message.from_user)

    if is_new and payload.startswith("ref") and payload[3:].isdigit():
        referrer_id = int(payload[3:])
        referrer = await session.get(User, referrer_id) if referrer_id != user.id else None
        if referrer is not None:
            user.referred_by_id = referrer_id
            bonus = await get_setting_int(session, "referral_bonus_tokens")
            referrer.tokens += bonus
            await session.commit()
            new_name = f"@{user.username}" if user.username else (user.full_name or str(user.id))
            with contextlib.suppress(Exception):
                await bot.send_message(referrer_id, f"🎉 По твоей реферальной ссылке присоединился {new_name}! Начислено +{bonus} 🪙")

    text = await get_setting(session, "start_text")
    await message.answer(text, parse_mode="HTML")


@router.message(Command("invite"))
async def cmd_invite(message: Message, session: AsyncSession, bot: Bot) -> None:
    user = await get_or_create_user(session, message.from_user)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref{user.id}"

    result = await session.execute(select(func.count()).select_from(User).where(User.referred_by_id == user.id))
    count = result.scalar_one()
    bonus = await get_setting_int(session, "referral_bonus_tokens")

    await message.answer(
        f"🔗 <b>Твоя реферальная ссылка</b>\n\n{link}\n\n"
        f"За каждого друга, который запустит бота по этой ссылке впервые, тебе начислится {bonus} 🪙.\n"
        f"Приглашено уже: {count} чел.",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message, session: AsyncSession) -> None:
    text = await get_setting(session, "help_text")
    await message.answer(text, parse_mode="HTML")


@router.message(Command("card", "wwg", "pull"))
async def cmd_card(message: Message, session: AsyncSession, bot: Bot) -> None:
    user = await get_or_create_user(session, message.from_user)

    cooldown_minutes = await get_setting_int(session, "cooldown_minutes")
    remaining = seconds_until_ready(user, cooldown_minutes)
    if remaining > 0:
        price = await get_setting_int(session, "extra_roll_price")
        affordable = user.tokens >= price
        await message.answer(
            f"⏳ Следующую бесплатную карточку можно будет получить через: {fmt_seconds(remaining)}\n"
            f"Можно взять доп. ролл за токены прямо сейчас.",
            reply_markup=buy_roll_kb(price, affordable),
        )
        return

    result = await pull_card(session, user)
    if result is None:
        await message.answer("Пока в пуле нет ни одной карточки — загляните позже 🙏")
        return

    dup_note = _pull_result_caption(result)
    await send_card(bot, message.chat.id, session, result.card, extra_caption=dup_note)


def _pull_result_caption(result) -> str:
    if result.is_duplicate:
        return f"🔁 Дубликат (копия №{result.copies_owned})\n💰 Токены: +{result.tokens_awarded} (с бонусом за дубль)"
    return f"✨ Новая карточка в коллекции!\n💰 Токены: +{result.tokens_awarded}"


@router.callback_query(F.data == "buyroll")
async def cb_buy_roll(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    user = await get_or_create_user(session, callback.from_user)
    outcome = await buy_extra_roll(session, user)
    if outcome is None:
        await callback.answer("Не хватает токенов 💸", show_alert=True)
        return

    result, price = outcome
    await callback.answer(f"Куплено за {price} 🪙")
    with contextlib.suppress(Exception):
        await callback.message.delete()
    dup_note = _pull_result_caption(result) + f"\n(куплено за {price} 🪙)"
    await send_card(bot, callback.message.chat.id, session, result.card, extra_caption=dup_note)


@router.message(Command("cases"))
async def cmd_cases(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(session, message.from_user)
    cases = await list_active_cases(session)
    if not cases:
        await message.answer("Пока нет доступных кейсов.")
        return

    lines = ["🎁 <b>Доступные кейсы</b>\n", f"💰 Твои токены: {user.tokens}\n"]
    for c in cases:
        rarities = ", ".join(o.rarity.name for o in c.odds if o.weight > 0)
        lines.append(f"<b>{c.name}</b> — {c.price_tokens} 🪙")
        if c.description:
            lines.append(c.description)
        if rarities:
            lines.append(f"Содержимое: {rarities}")
        lines.append("")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=cases_list_kb(cases, user.tokens))


@router.callback_query(F.data.startswith("opencase:"))
async def cb_open_case(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    case_id = int(callback.data.split(":")[1])
    case = await get_case(session, case_id)
    if case is None or not case.is_active:
        await callback.answer("Этот кейс сейчас недоступен.", show_alert=True)
        return

    user = await get_or_create_user(session, callback.from_user)
    result = await open_case(session, user, case)
    if result is None:
        await callback.answer("Не хватает токенов или кейс пуст 💸", show_alert=True)
        return

    await callback.answer(f"Кейс открыт за {case.price_tokens} 🪙")
    dup_note = _pull_result_caption(result) + f"\n(из кейса «{case.name}»)"
    await send_card(bot, callback.message.chat.id, session, result.card, extra_caption=dup_note)


async def _profile_text(session: AsyncSession, user: User, display_name: str) -> str:
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

    return (
        f"👤 <b>Профиль {display_name}</b>\n\n"
        f"💰 Токены: {user.tokens}\n"
        f"🎴 Собрано уникальных: {unique_owned}/{total_cards}\n"
        f"📦 Всего карточек получено: {total_pulls}\n"
        f"🕒 Следующая карта: {cooldown_line}"
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    user = await get_or_create_user(session, message.from_user)
    text = await _profile_text(session, user, message.from_user.full_name)
    await message.answer(text, parse_mode="HTML", reply_markup=profile_kb(user.hide_from_top))


@router.callback_query(F.data == "toggletop")
async def cb_toggle_top(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_or_create_user(session, callback.from_user)
    user.hide_from_top = not user.hide_from_top
    await session.commit()
    text = await _profile_text(session, user, callback.from_user.full_name)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=profile_kb(user.hide_from_top))
    await callback.answer("Теперь ты скрыт(а) из /top 🙈" if user.hide_from_top else "Теперь ты снова виден(на) в /top 👁")


async def _owned_cards(session: AsyncSession, user_id: int) -> list[UserCard]:
    result = await session.execute(
        select(UserCard)
        .where(UserCard.user_id == user_id)
        .options(selectinload(UserCard.card).selectinload(Card.rarity))
        .join(Card)
        .order_by(Card.name)
    )
    return list(result.scalars().all())


def _mycards_text_for_page(owned: list[UserCard], page: int) -> tuple[str, int]:
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
    owned = await _owned_cards(session, message.from_user.id)
    text, total_pages = _mycards_text_for_page(owned, 0)
    kb = mycards_kb(0, total_pages) if owned else None
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("mycards:"))
async def cb_mycards_page(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[1])
    owned = await _owned_cards(session, callback.from_user.id)
    text, total_pages = _mycards_text_for_page(owned, page)
    kb = mycards_kb(page, total_pages) if owned else None
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mygallery:"))
async def cb_mycards_gallery(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    arg = callback.data.split(":", 1)[1]
    owned = await _owned_cards(session, callback.from_user.id)
    if not owned:
        await callback.answer("У тебя пока нет карточек.", show_alert=True)
        return

    if arg == "list":
        with contextlib.suppress(Exception):
            await callback.message.delete()
        text, total_pages = _mycards_text_for_page(owned, 0)
        await bot.send_message(
            callback.message.chat.id, text, parse_mode="HTML", reply_markup=mycards_kb(0, total_pages)
        )
        await callback.answer()
        return

    index = max(0, min(int(arg), len(owned) - 1))
    uc = owned[index]
    with contextlib.suppress(Exception):
        await callback.message.delete()
    extra = f"У тебя: ×{uc.count}" if uc.count > 1 else ""
    await send_card(
        bot,
        callback.message.chat.id,
        session,
        uc.card,
        extra_caption=extra,
        reply_markup=mycards_gallery_kb(index, len(owned), uc.card),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


async def _top_text(session: AsyncSession, mode: str) -> str:
    medals = ["🥇", "🥈", "🥉"]

    if mode == "cards":
        result = await session.execute(
            select(User, func.coalesce(func.sum(UserCard.count), 0))
            .outerjoin(UserCard, UserCard.user_id == User.id)
            .where(User.hide_from_top.is_(False))
            .group_by(User.id)
            .order_by(func.coalesce(func.sum(UserCard.count), 0).desc())
            .limit(10)
        )
        rows = [row for row in result.all() if row[1] > 0]
        if not rows:
            return "Пока никто не собрал ни одной карточки."
        lines = ["🏆 <b>Топ по карточкам</b>\n"]
        for i, (u, total) in enumerate(rows):
            prefix = medals[i] if i < 3 else f"{i + 1}."
            name = u.full_name or (f"@{u.username}" if u.username else str(u.id))
            lines.append(f"{prefix} {name} — {total} 🎴")
        return "\n".join(lines)

    result = await session.execute(
        select(User).where(User.hide_from_top.is_(False)).order_by(User.tokens.desc()).limit(10)
    )
    top_users = list(result.scalars().all())
    if not top_users:
        return "Пока никто не собрал ни одного токена."
    lines = ["🏆 <b>Топ по токенам</b>\n"]
    for i, u in enumerate(top_users):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        name = u.full_name or (f"@{u.username}" if u.username else str(u.id))
        lines.append(f"{prefix} {name} — {u.tokens} 💰")
    return "\n".join(lines)


@router.message(Command("top"))
async def cmd_top(message: Message, session: AsyncSession) -> None:
    text = await _top_text(session, "tokens")
    await message.answer(text, parse_mode="HTML", reply_markup=top_kb("tokens"))


@router.callback_query(F.data.startswith("top:"))
async def cb_top_switch(callback: CallbackQuery, session: AsyncSession) -> None:
    mode = callback.data.split(":", 1)[1]
    text = await _top_text(session, mode)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=top_kb(mode))
    await callback.answer()

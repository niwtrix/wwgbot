import contextlib
import random
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.cards_repo import find_card_by_query, get_card, get_rarity, list_active_cards, list_all_cards, list_rarities
from app.db.models import Card, Rarity, User, UserCard
from app.db.settings_repo import get_setting, set_setting
from app.filters.owner import IsOwner
from app.keyboards.admin import (
    admin_main_menu,
    back_to_main_kb,
    card_edit_menu_kb,
    cards_list_kb,
    confirm_delete_card_kb,
    confirm_delete_rarity_kb,
    rarities_list_kb,
    rarity_edit_menu_kb,
    rarity_picker_kb,
    settings_menu_kb,
)
from app.services.card_sender import send_card
from app.states.admin import EditCardField, EditRarityField, EditSetting, EmojiCapture, NewCard, NewRarity

router = Router(name="admin")
router.message.filter(IsOwner())
router.callback_query.filter(IsOwner())

CARD_FIELD_LABELS = {
    "name": "имя",
    "role": "роль/статус",
    "quote": "цитату",
    "telegram_url": "ссылку на Telegram",
    "youtube_url": "ссылку на YouTube",
    "twitch_url": "ссылку на Twitch",
}

RARITY_FIELD_LABELS = {
    "name": "название",
    "weight": "вес (число, влияет на шанс выпадения)",
    "token_reward": "награду токенами (целое число)",
    "emoji_fallback": "обычный emoji-заменитель",
    "emoji_id": "ID премиум emoji (custom_emoji_id)",
}

SETTING_LABELS = {
    "cooldown_minutes": "кулдаун между карточками, в минутах",
    "duplicate_bonus": "бонус токенов за дубликат карточки",
}

ADMIN_HELP_TEXT = (
    "🆘 <b>Справка для админов</b>\n\n"
    "<b>/admin</b> — открыть панель управления (всё делается кнопками).\n\n"
    "<b>/testcard [имя]</b> — показать карточку так, как её увидит игрок (кнопки, редкость, фото), "
    "без влияния на профиль/токены/кулдаун. Без аргумента — случайная активная карточка.\n\n"
    "<b>Карточки участников</b>\n"
    "— список всех карточек, добавление нового участника, редактирование имени/роли/цитаты/ссылок, "
    "замена фото (просто пришли новое фото в чат), смена редкости, деактивация без удаления, удаление насовсем.\n\n"
    "<b>Редкости</b>\n"
    "— свои уровни редкости: название, вес (чем больше вес — тем чаще выпадает), награда токенами, "
    "запасной emoji и ID премиум-эмодзи. Можно добавлять новые уровни и удалять неиспользуемые "
    "(если к редкости привязаны карточки — сначала перепривяжи их к другой).\n\n"
    "<b>Настройки</b>\n"
    "— кулдаун между получениями карточек и бонус токенов за дубликат.\n\n"
    "<b>ID эмодзи</b>\n"
    "— чтобы использовать свой премиум-эмодзи как иконку редкости, пришли его текстом в чат "
    "(вставь эмодзи из своей Premium-панели, не обычный смайл с клавиатуры) — бот пришлёт в ответ "
    "его custom_emoji_id. Дальше вставь этот ID в редкость через 'ID премиум emoji'.\n"
    "⚠️ Если прислать обычный unicode-эмодзи (не премиум), ID получить не получится — Telegram присваивает "
    "custom_emoji_id только настоящим кастомным эмодзи.\n\n"
    "<b>Статистика</b> — сводка по игрокам, карточкам и токенам.\n\n"
    "Во время любого шага редактирования можно прислать /cancel, чтобы отменить ввод."
)


async def _safe_delete(message: Message) -> None:
    with contextlib.suppress(Exception):
        await message.delete()


async def _show_card(callback: CallbackQuery, session: AsyncSession, bot: Bot, card_id: int) -> None:
    card = await get_card(session, card_id)
    if card is None:
        await callback.answer("Карточка не найдена", show_alert=True)
        return
    await _safe_delete(callback.message)
    status = "активна ✅" if card.is_active else "деактивирована 🚫"
    await send_card(
        bot,
        callback.message.chat.id,
        session,
        card,
        extra_caption=f"(статус: {status})",
        reply_markup=card_edit_menu_kb(card),
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer("🛠 <b>Панель администратора WWGang Cards</b>", parse_mode="HTML", reply_markup=admin_main_menu())


@router.message(Command("adminhelp"))
async def cmd_adminhelp(message: Message) -> None:
    await message.answer(ADMIN_HELP_TEXT, parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Отменено.", reply_markup=admin_main_menu())


@router.message(Command("testcard"))
async def cmd_testcard(message: Message, session: AsyncSession, bot: Bot) -> None:
    query = message.text.split(maxsplit=1)
    card = None
    if len(query) > 1:
        card = await find_card_by_query(session, query[1].strip())
        if card is None:
            await message.answer(f"Не нашёл карточку по запросу «{query[1].strip()}». Проверь имя/slug.")
            return
    else:
        cards = await list_active_cards(session)
        if not cards:
            await message.answer("В пуле пока нет активных карточек.")
            return
        card = random.choice(cards)

    await send_card(
        bot,
        message.chat.id,
        session,
        card,
        extra_caption="🧪 Тестовый показ — не влияет на профиль, токены и кулдаун.",
    )


@router.message(Command("getemojiid"))
async def cmd_getemojiid(message: Message, state: FSMContext) -> None:
    await state.set_state(EmojiCapture.waiting_emoji)
    await message.answer(
        "Пришли сообщение с нужным премиум-эмодзи (вставь его из панели эмодзи в Telegram Premium), "
        "и я пришлю в ответ его custom_emoji_id."
    )


@router.callback_query(F.data == "adm:main")
async def cb_main(callback: CallbackQuery) -> None:
    await _safe_delete(callback.message)
    await callback.message.answer(
        "🛠 <b>Панель администратора WWGang Cards</b>", parse_mode="HTML", reply_markup=admin_main_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "adm:help")
async def cb_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(ADMIN_HELP_TEXT, parse_mode="HTML", reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:getemoji")
async def cb_getemoji(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EmojiCapture.waiting_emoji)
    await callback.message.edit_text(
        "Пришли сообщение с нужным премиум-эмодзи (вставь его из панели эмодзи Telegram Premium), "
        "и я пришлю в ответ его custom_emoji_id.",
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()


@router.message(EmojiCapture.waiting_emoji)
async def on_emoji_capture(message: Message, state: FSMContext) -> None:
    entities = (message.entities or []) + (message.caption_entities or [])
    custom = [e for e in entities if e.type == "custom_emoji"]
    if not custom:
        await message.answer(
            "Не нашёл кастомный emoji в этом сообщении. Убедись, что вставляешь эмодзи именно из панели "
            "премиум-эмодзи, а не обычный смайл с клавиатуры. Попробуй ещё раз или /cancel."
        )
        return
    lines = ["Нашёл:"]
    text = message.text or message.caption or ""
    for e in custom:
        piece = text[e.offset : e.offset + e.length]
        lines.append(f"{piece} → <code>{e.custom_emoji_id}</code>")
    await state.clear()
    await message.answer("\n".join(lines), parse_mode="HTML")


# ---------- Cards list / detail ----------


@router.callback_query(F.data.startswith("adm:cards:"))
async def cb_cards_list(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[2])
    cards = await list_all_cards(session)
    await _safe_delete(callback.message)
    await callback.message.answer(
        f"📇 <b>Карточки участников</b> ({len(cards)} всего)", parse_mode="HTML", reply_markup=cards_list_kb(cards, page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:card:"))
async def cb_card_detail(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    card_id = int(callback.data.split(":")[2])
    await _show_card(callback, session, bot, card_id)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:ctoggle:"))
async def cb_card_toggle(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    card_id = int(callback.data.split(":")[2])
    card = await get_card(session, card_id)
    if card:
        card.is_active = not card.is_active
        await session.commit()
    await _show_card(callback, session, bot, card_id)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cdelask:"))
async def cb_card_delete_ask(callback: CallbackQuery) -> None:
    card_id = int(callback.data.split(":")[2])
    await callback.message.edit_reply_markup(reply_markup=confirm_delete_card_kb(card_id))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cdelyes:"))
async def cb_card_delete_yes(callback: CallbackQuery, session: AsyncSession) -> None:
    card_id = int(callback.data.split(":")[2])
    card = await get_card(session, card_id)
    if card:
        await session.delete(card)
        await session.commit()
    await _safe_delete(callback.message)
    cards = await list_all_cards(session)
    await callback.message.answer(
        "🗑 Карточка удалена.", reply_markup=cards_list_kb(cards, 0)
    )
    await callback.answer()


# ---------- Edit card field (generic text field) ----------


@router.callback_query(F.data.startswith("adm:cfield:"))
async def cb_card_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, card_id, field = callback.data.split(":")
    await state.set_state(EditCardField.waiting_value)
    await state.update_data(card_id=int(card_id), field=field)
    label = CARD_FIELD_LABELS.get(field, field)
    await callback.message.answer(f"Пришли новое значение поля «{label}» (или /cancel):")
    await callback.answer()


@router.message(EditCardField.waiting_value)
async def on_card_field_value(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    data = await state.get_data()
    card = await get_card(session, data["card_id"])
    if card is None:
        await state.clear()
        await message.answer("Карточка больше не существует.")
        return
    value = (message.text or "").strip()
    field = data["field"]
    if value == "-":
        value = ""
    if field in ("telegram_url", "youtube_url", "twitch_url"):
        setattr(card, field, value or None)
    else:
        setattr(card, field, value)
    await session.commit()
    await state.clear()
    await message.answer("✅ Обновлено.")
    await send_card(bot, message.chat.id, session, card, reply_markup=card_edit_menu_kb(card))


@router.callback_query(F.data.startswith("adm:cphoto:"))
async def cb_card_photo(callback: CallbackQuery, state: FSMContext) -> None:
    card_id = int(callback.data.split(":")[2])
    await state.set_state(EditCardField.waiting_photo)
    await state.update_data(card_id=card_id)
    await callback.message.answer("Пришли новое фото для этой карточки (как фото, не файлом), или /cancel:")
    await callback.answer()


@router.message(EditCardField.waiting_photo, F.photo)
async def on_card_photo_value(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    data = await state.get_data()
    card = await get_card(session, data["card_id"])
    await state.clear()
    if card is None:
        await message.answer("Карточка больше не существует.")
        return
    card.tg_file_id = message.photo[-1].file_id
    await session.commit()
    await message.answer("✅ Фото обновлено.")
    await send_card(bot, message.chat.id, session, card, reply_markup=card_edit_menu_kb(card))


@router.message(EditCardField.waiting_photo)
async def on_card_photo_wrong(message: Message) -> None:
    await message.answer("Это не похоже на фото. Пришли изображение или /cancel.")


@router.callback_query(F.data.startswith("adm:crarity:"))
async def cb_card_rarity_pick(callback: CallbackQuery, session: AsyncSession) -> None:
    card_id = int(callback.data.split(":")[2])
    rarities = await list_rarities(session)
    await callback.message.edit_reply_markup(reply_markup=rarity_picker_kb(rarities, card_id))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:setrarity:"))
async def cb_card_rarity_set(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    _, _, card_id, rarity_id = callback.data.split(":")
    card = await get_card(session, int(card_id))
    if card:
        card.rarity_id = rarity_id
        await session.commit()
    await _show_card(callback, session, bot, int(card_id))
    await callback.answer("Редкость обновлена")


# ---------- New card wizard ----------


@router.callback_query(F.data == "adm:newcard")
async def cb_newcard_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewCard.name)
    await state.update_data({})
    await callback.message.answer("Новый участник. Пришли имя (как будет отображаться на карточке), или /cancel:")
    await callback.answer()


@router.message(NewCard.name)
async def on_newcard_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(NewCard.role)
    await message.answer("Роль/статус (например «Участник WWGang»), или «-» чтобы пропустить:")


@router.message(NewCard.role)
async def on_newcard_role(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    await state.update_data(role="" if value == "-" else value)
    await state.set_state(NewCard.quote)
    await message.answer("Цитата для карточки, или «-» чтобы пропустить:")


@router.message(NewCard.quote)
async def on_newcard_quote(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    await state.update_data(quote="" if value == "-" else value)
    await state.set_state(NewCard.telegram)
    await message.answer("Ссылка на Telegram, или «-» чтобы пропустить:")


@router.message(NewCard.telegram)
async def on_newcard_telegram(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    await state.update_data(telegram=None if value == "-" else value)
    await state.set_state(NewCard.youtube)
    await message.answer("Ссылка на YouTube, или «-» чтобы пропустить:")


@router.message(NewCard.youtube)
async def on_newcard_youtube(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    await state.update_data(youtube=None if value == "-" else value)
    await state.set_state(NewCard.twitch)
    await message.answer("Ссылка на Twitch, или «-» чтобы пропустить:")


@router.message(NewCard.twitch)
async def on_newcard_twitch(message: Message, state: FSMContext, session: AsyncSession) -> None:
    value = message.text.strip()
    await state.update_data(twitch=None if value == "-" else value)
    await state.set_state(NewCard.rarity)
    rarities = await list_rarities(session)
    lines = ["Выбери редкость, пришли её название текстом:"]
    lines += [f"— {r.name}" for r in rarities]
    await message.answer("\n".join(lines))


@router.message(NewCard.rarity)
async def on_newcard_rarity(message: Message, state: FSMContext, session: AsyncSession) -> None:
    rarities = await list_rarities(session)
    match = next((r for r in rarities if r.name.lower() == message.text.strip().lower()), None)
    if match is None:
        names = ", ".join(r.name for r in rarities)
        await message.answer(f"Не нашёл такую редкость. Доступны: {names}")
        return
    await state.update_data(rarity_id=match.id)
    await state.set_state(NewCard.photo)
    await message.answer("Пришли фото для карточки (или «-» чтобы добавить без фото сейчас):")


async def _unique_slug(session: AsyncSession, name: str) -> str:
    slug_base = re.sub(r"[^a-z0-9_]+", "", name.lower()) or "card"
    slug = slug_base
    n = 1
    while (await session.execute(select(Card).where(Card.slug == slug))).scalar_one_or_none():
        n += 1
        slug = f"{slug_base}{n}"
    return slug


async def _create_card_from_state(session: AsyncSession, data: dict, tg_file_id: str | None) -> Card:
    card = Card(
        slug=await _unique_slug(session, data["name"]),
        name=data["name"],
        role=data.get("role", ""),
        quote=data.get("quote", ""),
        telegram_url=data.get("telegram"),
        youtube_url=data.get("youtube"),
        twitch_url=data.get("twitch"),
        tg_file_id=tg_file_id,
        rarity_id=data["rarity_id"],
    )
    session.add(card)
    await session.commit()
    return card


@router.message(NewCard.photo, F.photo)
async def on_newcard_photo(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    card = await _create_card_from_state(session, data, message.photo[-1].file_id)
    await state.clear()
    await message.answer(f"✅ Карточка «{card.name}» добавлена в пул.", reply_markup=admin_main_menu())


@router.message(NewCard.photo)
async def on_newcard_photo_skip(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if (message.text or "").strip() != "-":
        await message.answer("Пришли фото или «-» чтобы пропустить.")
        return
    data = await state.get_data()
    card = await _create_card_from_state(session, data, None)
    await state.clear()
    await message.answer(
        f"✅ Карточка «{card.name}» добавлена в пул (без фото — добавь его позже).",
        reply_markup=admin_main_menu(),
    )


# ---------- Rarities ----------


@router.callback_query(F.data == "adm:rarities")
async def cb_rarities_list(callback: CallbackQuery, session: AsyncSession) -> None:
    rarities = await list_rarities(session)
    await callback.message.edit_text(
        "🏷 <b>Уровни редкости</b>\nЧем больше вес — тем чаще выпадает уровень.",
        parse_mode="HTML",
        reply_markup=rarities_list_kb(rarities),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:rarity:"))
async def cb_rarity_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    rarity_id = callback.data.split(":")[2]
    rarity = await get_rarity(session, rarity_id)
    if rarity is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    result = await session.execute(select(func.count()).select_from(Card).where(Card.rarity_id == rarity_id))
    count = result.scalar_one()
    emoji_id_text = rarity.emoji_id or "не задан"
    text = (
        f"🏷 <b>{rarity.name}</b>\n\n"
        f"Вес: {rarity.weight:g}\n"
        f"Награда токенами: {rarity.token_reward}\n"
        f"Запасной emoji: {rarity.emoji_fallback}\n"
        f"Премиум emoji ID: <code>{emoji_id_text}</code>\n"
        f"Карточек с этой редкостью: {count}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=rarity_edit_menu_kb(rarity))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:rfield:"))
async def cb_rarity_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, rarity_id, field = callback.data.split(":")
    await state.set_state(EditRarityField.waiting_value)
    await state.update_data(rarity_id=rarity_id, field=field)
    label = RARITY_FIELD_LABELS.get(field, field)
    extra = ""
    if field == "emoji_id":
        extra = " (используй /getemojiid, если ещё не знаешь ID; пришли «-» чтобы очистить)"
    await callback.message.answer(f"Пришли новое значение поля «{label}»{extra}, или /cancel:")
    await callback.answer()


@router.message(EditRarityField.waiting_value)
async def on_rarity_field_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    rarity = await get_rarity(session, data["rarity_id"])
    if rarity is None:
        await state.clear()
        await message.answer("Редкость больше не существует.")
        return
    field = data["field"]
    raw = message.text.strip()

    if field == "weight":
        try:
            rarity.weight = float(raw.replace(",", "."))
        except ValueError:
            await message.answer("Нужно число, например 15 или 7.5. Попробуй ещё раз:")
            return
    elif field == "token_reward":
        try:
            rarity.token_reward = int(raw)
        except ValueError:
            await message.answer("Нужно целое число. Попробуй ещё раз:")
            return
    elif field == "emoji_id":
        rarity.emoji_id = None if raw == "-" else raw
    else:
        setattr(rarity, field, raw)

    await session.commit()
    await state.clear()
    await message.answer(f"✅ Обновлено: {rarity.name}", reply_markup=back_to_main_kb())


@router.callback_query(F.data == "adm:newrarity")
async def cb_newrarity_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewRarity.name)
    await callback.message.answer("Название нового уровня редкости, или /cancel:")
    await callback.answer()


@router.message(NewRarity.name)
async def on_newrarity_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(NewRarity.weight)
    await message.answer("Вес (число, влияет на шанс выпадения, например 10):")


@router.message(NewRarity.weight)
async def on_newrarity_weight(message: Message, state: FSMContext) -> None:
    try:
        weight = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Нужно число. Попробуй ещё раз:")
        return
    await state.update_data(weight=weight)
    await state.set_state(NewRarity.token_reward)
    await message.answer("Награда токенами за карточку этой редкости (целое число):")


@router.message(NewRarity.token_reward)
async def on_newrarity_token_reward(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        token_reward = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно целое число. Попробуй ещё раз:")
        return
    data = await state.get_data()

    slug_base = re.sub(r"[^a-z0-9_]+", "", data["name"].lower()) or "rarity"
    slug = slug_base
    n = 1
    while await session.get(Rarity, slug):
        n += 1
        slug = f"{slug_base}{n}"

    result = await session.execute(select(func.max(Rarity.sort_order)))
    max_order = result.scalar_one() or 0

    rarity = Rarity(
        id=slug,
        name=data["name"],
        weight=data["weight"],
        token_reward=token_reward,
        emoji_fallback="🔸",
        sort_order=max_order + 1,
    )
    session.add(rarity)
    await session.commit()
    await state.clear()
    await message.answer(f"✅ Редкость «{rarity.name}» создана.", reply_markup=admin_main_menu())


@router.callback_query(F.data.startswith("adm:rdelask:"))
async def cb_rarity_delete_ask(callback: CallbackQuery) -> None:
    rarity_id = callback.data.split(":")[2]
    await callback.message.edit_reply_markup(reply_markup=confirm_delete_rarity_kb(rarity_id))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:rdelyes:"))
async def cb_rarity_delete_yes(callback: CallbackQuery, session: AsyncSession) -> None:
    rarity_id = callback.data.split(":")[2]
    result = await session.execute(select(func.count()).select_from(Card).where(Card.rarity_id == rarity_id))
    count = result.scalar_one()
    if count > 0:
        await callback.answer(
            f"Нельзя удалить: к этой редкости привязано карточек — {count}. Сначала смени им редкость.",
            show_alert=True,
        )
        return
    rarity = await get_rarity(session, rarity_id)
    if rarity:
        await session.delete(rarity)
        await session.commit()
    rarities = await list_rarities(session)
    await callback.message.edit_text(
        "🗑 Редкость удалена.", reply_markup=rarities_list_kb(rarities)
    )
    await callback.answer()


# ---------- Settings ----------


@router.callback_query(F.data == "adm:settings")
async def cb_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    cooldown = await get_setting(session, "cooldown_minutes")
    dup_bonus = await get_setting(session, "duplicate_bonus")
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"Кулдаун: {cooldown} мин\n"
        f"Бонус токенов за дубль: {dup_bonus}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=settings_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("adm:sfield:"))
async def cb_setting_field(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[2]
    await state.set_state(EditSetting.waiting_value)
    await state.update_data(key=key)
    label = SETTING_LABELS.get(key, key)
    await callback.message.answer(f"Пришли новое значение для «{label}» (целое число), или /cancel:")
    await callback.answer()


@router.message(EditSetting.waiting_value)
async def on_setting_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    raw = message.text.strip()
    try:
        int(raw)
    except ValueError:
        await message.answer("Нужно целое число. Попробуй ещё раз:")
        return
    await set_setting(session, data["key"], raw)
    await state.clear()
    await message.answer("✅ Настройка обновлена.", reply_markup=back_to_main_kb())


# ---------- Stats ----------


@router.callback_query(F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    users_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    cards_count = (await session.execute(select(func.count()).select_from(Card))).scalar_one()
    active_cards_count = (
        await session.execute(select(func.count()).select_from(Card).where(Card.is_active.is_(True)))
    ).scalar_one()
    total_pulls = (await session.execute(select(func.coalesce(func.sum(UserCard.count), 0)))).scalar_one()
    total_tokens = (await session.execute(select(func.coalesce(func.sum(User.tokens), 0)))).scalar_one()

    rarities = await list_rarities(session)
    lines = [
        "📊 <b>Статистика</b>\n",
        f"Игроков: {users_count}",
        f"Карточек в пуле: {cards_count} (активных: {active_cards_count})",
        f"Всего вытянуто карточек: {total_pulls}",
        f"Всего токенов на руках: {total_tokens}\n",
        "По редкости:",
    ]
    for r in rarities:
        c = (await session.execute(select(func.count()).select_from(Card).where(Card.rarity_id == r.id))).scalar_one()
        lines.append(f"{r.emoji_fallback} {r.name}: {c} карточек")

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()

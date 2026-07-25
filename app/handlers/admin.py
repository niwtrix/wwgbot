import asyncio
import contextlib
import random
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.activity_repo import EVENT_LABELS, list_events, log_event
from app.db.cards_repo import find_card_by_query, get_card, get_rarity, list_active_cards, list_all_cards, list_rarities
from app.db.cases_repo import get_case, list_cases, set_case_odds
from app.db.models import Card, Case, Rarity, User, UserCard
from app.db.settings_repo import get_setting, set_setting
from app.filters.owner import IsOwner
from app.keyboards.admin import (
    activity_log_kb,
    admin_main_menu,
    back_to_main_kb,
    card_edit_menu_kb,
    cards_list_kb,
    case_edit_menu_kb,
    case_odds_kb,
    cases_list_kb,
    confirm_broadcast_kb,
    confirm_delete_card_kb,
    confirm_delete_case_kb,
    confirm_delete_rarity_kb,
    rarities_list_kb,
    rarity_edit_menu_kb,
    rarity_picker_kb,
    settings_menu_kb,
    users_list_kb,
)
from app.services.card_sender import send_card
from app.services.health_report import build_status_report
from app.states.admin import (
    BroadcastMessage,
    EditCardField,
    EditCaseField,
    EditCaseOdds,
    EditRarityField,
    EditSetting,
    EmojiCapture,
    GrantTokens,
    NewCard,
    NewCase,
    NewRarity,
)

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
    "start_text": "текст команды /start",
    "help_text": "текст команды /help",
    "referral_bonus_tokens": "бонус токенов за приглашённого друга (реферала)",
    "daily_bonus_base_tokens": "базовый ежедневный бонус (токены)",
    "daily_bonus_streak_step": "прирост бонуса за каждый день серии подряд",
    "daily_bonus_max_tokens": "максимум ежедневного бонуса (токены)",
}

TEXT_SETTING_KEYS = {"start_text", "help_text"}

ADMIN_HELP_TEXT = (
    "🆘 <b>Справка для админов</b>\n\n"
    "<b>/admin</b> — открыть панель управления (всё делается кнопками).\n\n"
    "<b>/testcard [имя или редкость]</b> — показать карточку так, как её увидит игрок (кнопки, редкость, фото), "
    "без влияния на профиль/токены/кулдаун. По имени/slug — конкретную карточку, по названию редкости "
    "(например «Легендарная») — случайную карточку этой редкости. Без аргумента — случайная активная карточка.\n\n"
    "<b>Карточки участников</b>\n"
    "— список всех карточек, добавление нового участника, редактирование имени/роли/цитаты/ссылок, "
    "замена фото (просто пришли новое фото в чат), смена редкости, деактивация без удаления, удаление насовсем.\n\n"
    "<b>Редкости</b>\n"
    "— свои уровни редкости: название, вес (чем больше вес — тем чаще выпадает), награда токенами, "
    "запасной emoji и ID премиум-эмодзи. «Только из кейсов» — редкость исключается из обычного ролла "
    "(например Хроматическая — доступна только через кейсы). Можно добавлять новые уровни и удалять "
    "неиспользуемые (если к редкости привязаны карточки — сначала перепривяжи их к другой).\n\n"
    "<b>Кейсы</b>\n"
    "— покупаются за токены, содержимое задаётся отдельными шансами по редкости (не связано с шансами "
    "обычного ролла). Создание, цена, описание, вкл/выкл, удаление, редактирование содержимого.\n\n"
    "<b>Настройки</b>\n"
    "— кулдаун между картами, бонус токенов за дубликат, цена доп. ролла за токены, параметры защиты "
    "от дублей (мин. кол-во пуллов до повтора карты, сколько пуллов идёт восстановление шанса, "
    "минимальная доля шанса сразу после порога), вкл/выкл и интервал автоотчётов о статусе бота в личку, "
    "тексты команд /start и /help (можно с HTML-разметкой).\n\n"
    "<b>ID эмодзи</b>\n"
    "— чтобы использовать свой премиум-эмодзи как иконку редкости, пришли его текстом в чат "
    "(вставь эмодзи из своей Premium-панели, не обычный смайл с клавиатуры) — бот пришлёт в ответ "
    "его custom_emoji_id. Дальше вставь этот ID в редкость через 'ID премиум emoji'.\n"
    "⚠️ Если прислать обычный unicode-эмодзи (не премиум), ID получить не получится — Telegram присваивает "
    "custom_emoji_id только настоящим кастомным эмодзи.\n\n"
    "<b>Статистика</b> — сводка по игрокам, карточкам и токенам.\n\n"
    "<b>Пользователи</b> — список всех, кто запускал бота, с токенами.\n\n"
    "<b>Начислить токены</b> — начислить (или списать, если ввести число со знаком минус) "
    "токены игроку по его ID или @username.\n\n"
    "<b>Рассылка</b> — пришли любое сообщение (текст, фото и т.д.), подтверди — уйдёт всем пользователям бота.\n\n"
    "<b>/ping</b> — пинг Telegram и среднее время ответа бота прямо сейчас.\n\n"
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


@router.message(Command("ping"))
async def cmd_ping(message: Message, bot: Bot) -> None:
    await message.answer(await build_status_report(bot), parse_mode="HTML")


@router.message(Command("testcard"))
async def cmd_testcard(message: Message, session: AsyncSession, bot: Bot) -> None:
    query = message.text.split(maxsplit=1)
    card = None
    if len(query) > 1:
        raw_query = query[1].strip()
        card = await find_card_by_query(session, raw_query)
        if card is None:
            rarities = await list_rarities(session)
            matched_rarity = next(
                (r for r in rarities if r.id.lower() == raw_query.lower() or r.name.lower() == raw_query.lower()),
                None,
            )
            if matched_rarity is not None:
                cards = [c for c in await list_active_cards(session) if c.rarity_id == matched_rarity.id]
                if not cards:
                    await message.answer(f"В редкости «{matched_rarity.name}» пока нет активных карточек.")
                    return
                card = random.choice(cards)
            else:
                await message.answer(
                    f"Не нашёл карточку или редкость по запросу «{raw_query}». Проверь имя/slug/название редкости."
                )
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


@router.callback_query(F.data.startswith("adm:rtogglecaseonly:"))
async def cb_rarity_toggle_case_only(callback: CallbackQuery, session: AsyncSession) -> None:
    rarity_id = callback.data.split(":")[2]
    rarity = await get_rarity(session, rarity_id)
    if rarity is None:
        await callback.answer("Редкость не найдена.", show_alert=True)
        return
    rarity.case_only = not rarity.case_only
    await session.commit()
    await callback.message.edit_reply_markup(reply_markup=rarity_edit_menu_kb(rarity))
    await callback.answer("Обновлено")


# ---------- Settings ----------


async def _settings_text(session: AsyncSession) -> str:
    cooldown = await get_setting(session, "cooldown_minutes")
    dup_bonus = await get_setting(session, "duplicate_bonus")
    extra_roll_price = await get_setting(session, "extra_roll_price")
    pity_floor = await get_setting(session, "pity_floor_pulls")
    pity_ramp = await get_setting(session, "pity_ramp_pulls")
    pity_min = await get_setting(session, "pity_min_weight_fraction")
    hr_enabled = await get_setting(session, "health_report_enabled")
    hr_interval = await get_setting(session, "health_report_interval_minutes")
    referral_bonus = await get_setting(session, "referral_bonus_tokens")
    daily_base = await get_setting(session, "daily_bonus_base_tokens")
    daily_step = await get_setting(session, "daily_bonus_streak_step")
    daily_max = await get_setting(session, "daily_bonus_max_tokens")
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"Кулдаун: {cooldown} мин\n"
        f"Бонус токенов за дубль: {dup_bonus}\n"
        f"Цена доп. ролла: {extra_roll_price} 🪙\n"
        f"Защита от дублей: мин. {pity_floor} пуллов, восстановление за {pity_ramp} пуллов, "
        f"мин. доля шанса {pity_min}\n"
        f"Бонус токенов за реферала: {referral_bonus} 🪙\n"
        f"Ежедневный бонус: {daily_base} 🪙 база, +{daily_step} 🪙 за день серии, максимум {daily_max} 🪙\n"
        f"Отчёты о статусе: {'включены' if hr_enabled == '1' else 'выключены'}, каждые {hr_interval} мин"
    )


@router.callback_query(F.data == "adm:settings")
async def cb_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    hr_enabled = (await get_setting(session, "health_report_enabled")) == "1"
    await callback.message.edit_text(
        await _settings_text(session), parse_mode="HTML", reply_markup=settings_menu_kb(hr_enabled)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:togglehealthreport")
async def cb_toggle_health_report(callback: CallbackQuery, session: AsyncSession) -> None:
    current = await get_setting(session, "health_report_enabled")
    await set_setting(session, "health_report_enabled", "0" if current == "1" else "1")
    hr_enabled = (await get_setting(session, "health_report_enabled")) == "1"
    await callback.message.edit_text(
        await _settings_text(session), parse_mode="HTML", reply_markup=settings_menu_kb(hr_enabled)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:sfield:"))
async def cb_setting_field(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[2]
    await state.set_state(EditSetting.waiting_value)
    await state.update_data(key=key)
    label = SETTING_LABELS.get(key, key)
    if key == "pity_min_weight_fraction":
        hint = "число от 0 до 1, например 0.1"
    elif key in TEXT_SETTING_KEYS:
        hint = "текст сообщения, можно с HTML-разметкой (жирный, ссылки и т.д.)"
    else:
        hint = "целое число"
    await callback.message.answer(f"Пришли новое значение для «{label}» ({hint}), или /cancel:")
    await callback.answer()


@router.message(EditSetting.waiting_value)
async def on_setting_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    key = data["key"]

    if key in TEXT_SETTING_KEYS:
        raw = message.html_text or (message.text or "").strip()
        await set_setting(session, key, raw)
        await state.clear()
        await message.answer("✅ Текст обновлён.", reply_markup=back_to_main_kb())
        return

    raw = message.text.strip()
    if key == "pity_min_weight_fraction":
        try:
            value = float(raw.replace(",", "."))
            if not (0 <= value <= 1):
                raise ValueError
        except ValueError:
            await message.answer("Нужно число от 0 до 1, например 0.1. Попробуй ещё раз:")
            return
        raw = str(value)
    else:
        try:
            int(raw)
        except ValueError:
            await message.answer("Нужно целое число. Попробуй ещё раз:")
            return
    await set_setting(session, key, raw)
    await state.clear()
    await message.answer("✅ Настройка обновлена.", reply_markup=back_to_main_kb())


# ---------- Cases ----------

CASE_FIELD_LABELS = {
    "name": "название",
    "price_tokens": "цену (целое число токенов)",
    "description": "описание",
}


@router.callback_query(F.data == "adm:cases")
async def cb_cases_list(callback: CallbackQuery, session: AsyncSession) -> None:
    cases = await list_cases(session)
    await callback.message.edit_text(
        "🎁 <b>Кейсы</b>\n\nВыбери кейс или создай новый:", parse_mode="HTML", reply_markup=cases_list_kb(cases)
    )
    await callback.answer()


def _case_detail_text(case: Case) -> str:
    lines = [
        f"🎁 <b>{case.name}</b>\n",
        f"Цена: {case.price_tokens} 🪙",
        f"Статус: {'активен ✅' if case.is_active else 'выключен 🚫'}",
    ]
    if case.description:
        lines.append(f"Описание: {case.description}")
    lines.append("")
    lines.append("Содержимое:")
    if case.odds:
        for o in case.odds:
            lines.append(f"{o.rarity.emoji_fallback} {o.rarity.name}: вес {o.weight:g}")
    else:
        lines.append("— пусто, добавь редкости через «Содержимое» —")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("adm:case:"))
async def cb_case_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    case_id = int(callback.data.split(":")[2])
    case = await get_case(session, case_id)
    if case is None:
        await callback.answer("Кейс не найден.", show_alert=True)
        return
    await callback.message.edit_text(_case_detail_text(case), parse_mode="HTML", reply_markup=case_edit_menu_kb(case))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cafield:"))
async def cb_case_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, case_id, field = callback.data.split(":")
    await state.set_state(EditCaseField.waiting_value)
    await state.update_data(case_id=int(case_id), field=field)
    label = CASE_FIELD_LABELS.get(field, field)
    await callback.message.answer(f"Пришли новое значение для «{label}», или /cancel:")
    await callback.answer()


@router.message(EditCaseField.waiting_value)
async def on_case_field_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    case = await get_case(session, data["case_id"])
    if case is None:
        await state.clear()
        await message.answer("Кейс не найден.", reply_markup=back_to_main_kb())
        return

    field = data["field"]
    raw = message.text.strip()
    if field == "price_tokens":
        try:
            case.price_tokens = int(raw)
        except ValueError:
            await message.answer("Нужно целое число. Попробуй ещё раз:")
            return
    else:
        setattr(case, field, raw)

    await session.commit()
    await state.clear()
    await message.answer(f"✅ Обновлено: {case.name}", reply_markup=back_to_main_kb())


@router.callback_query(F.data == "adm:newcase")
async def cb_newcase_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewCase.name)
    await callback.message.answer("Название нового кейса, или /cancel:")
    await callback.answer()


@router.message(NewCase.name)
async def on_newcase_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(NewCase.price_tokens)
    await message.answer("Цена кейса в токенах (целое число):")


@router.message(NewCase.price_tokens)
async def on_newcase_price(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        price = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно целое число. Попробуй ещё раз:")
        return
    data = await state.get_data()

    slug_base = re.sub(r"[^a-z0-9_]+", "", data["name"].lower()) or "case"
    slug = slug_base
    n = 1
    while (await session.execute(select(Case).where(Case.slug == slug))).scalar_one_or_none():
        n += 1
        slug = f"{slug_base}{n}"

    result = await session.execute(select(func.max(Case.sort_order)))
    max_order = result.scalar_one() or 0

    case = Case(slug=slug, name=data["name"], price_tokens=price, sort_order=max_order + 1)
    session.add(case)
    await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Кейс «{case.name}» создан. Не забудь добавить содержимое через «Содержимое».",
        reply_markup=admin_main_menu(),
    )


@router.callback_query(F.data.startswith("adm:catoggle:"))
async def cb_case_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    case_id = int(callback.data.split(":")[2])
    case = await get_case(session, case_id)
    if case is None:
        await callback.answer("Кейс не найден.", show_alert=True)
        return
    case.is_active = not case.is_active
    await session.commit()
    await callback.message.edit_text(_case_detail_text(case), parse_mode="HTML", reply_markup=case_edit_menu_kb(case))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cadelask:"))
async def cb_case_delete_ask(callback: CallbackQuery) -> None:
    case_id = int(callback.data.split(":")[2])
    await callback.message.edit_reply_markup(reply_markup=confirm_delete_case_kb(case_id))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cadelyes:"))
async def cb_case_delete_yes(callback: CallbackQuery, session: AsyncSession) -> None:
    case_id = int(callback.data.split(":")[2])
    case = await get_case(session, case_id)
    if case:
        await session.delete(case)
        await session.commit()
    cases = await list_cases(session)
    await callback.message.edit_text("🗑 Кейс удалён.", reply_markup=cases_list_kb(cases))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:caodds:"))
async def cb_case_odds(callback: CallbackQuery, session: AsyncSession) -> None:
    case_id = int(callback.data.split(":")[2])
    case = await get_case(session, case_id)
    if case is None:
        await callback.answer("Кейс не найден.", show_alert=True)
        return
    rarities = await list_rarities(session)
    await callback.message.edit_text(
        f"🎲 <b>Содержимое кейса «{case.name}»</b>\n\n"
        "Тапни редкость, чтобы задать её вес в этом кейсе (0 — убрать из кейса).",
        parse_mode="HTML",
        reply_markup=case_odds_kb(case, rarities),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:casetrarity:"))
async def cb_case_odds_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, case_id, rarity_id = callback.data.split(":")
    await state.set_state(EditCaseOdds.waiting_value)
    await state.update_data(case_id=int(case_id), rarity_id=rarity_id)
    await callback.message.answer(
        "Пришли вес этой редкости в кейсе (число, 0 — убрать из кейса), или /cancel:"
    )
    await callback.answer()


@router.message(EditCaseOdds.waiting_value)
async def on_case_odds_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    raw = message.text.strip().replace(",", ".")
    try:
        weight = float(raw)
        if weight < 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно неотрицательное число, например 100 или 0. Попробуй ещё раз:")
        return

    await set_case_odds(session, data["case_id"], data["rarity_id"], weight)
    case = await get_case(session, data["case_id"])
    await state.clear()
    await message.answer(
        f"✅ Обновлено содержимое кейса «{case.name}».",
        reply_markup=back_to_main_kb(),
    )


# ---------- Users list ----------

USERS_PAGE_SIZE = 15


async def _users_page_text(session: AsyncSession, page: int) -> tuple[str, int]:
    result = await session.execute(select(User).order_by(User.joined_at))
    users = list(result.scalars().all())
    if not users:
        return "Пока нет ни одного пользователя.", 1

    total_pages = (len(users) + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    chunk = users[page * USERS_PAGE_SIZE : (page + 1) * USERS_PAGE_SIZE]

    lines = [f"👥 <b>Пользователи</b> ({len(users)} всего)\n"]
    for u in chunk:
        name = f"@{u.username}" if u.username else (u.full_name or "без имени")
        lines.append(f"<code>{u.id}</code> — {name} — {u.tokens} 🪙")
    return "\n".join(lines), total_pages


@router.callback_query(F.data.startswith("adm:users:"))
async def cb_users_list(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[2])
    text, total_pages = await _users_page_text(session, page)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=users_list_kb(page, total_pages))
    await callback.answer()


# ---------- Broadcast ----------


@router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastMessage.waiting_message)
    await callback.message.answer(
        "Пришли сообщение для рассылки всем пользователям бота (текст, фото, видео — что угодно), или /cancel:"
    )
    await callback.answer()


@router.message(BroadcastMessage.waiting_message)
async def on_broadcast_message(message: Message, state: FSMContext) -> None:
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(BroadcastMessage.waiting_confirm)
    await message.reply(
        "⬆️ Это сообщение уйдёт всем пользователям бота. Подтвердить?",
        reply_markup=confirm_broadcast_kb(),
    )


@router.callback_query(F.data == "adm:broadcastcancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")
    await callback.answer()


@router.callback_query(F.data == "adm:broadcastsend")
async def cb_broadcast_send(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_text("⏳ Рассылаю...")
    await callback.answer()

    result = await session.execute(select(User.id))
    user_ids = [row[0] for row in result.all()]

    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await callback.bot.copy_message(
                chat_id=user_id,
                from_chat_id=data["chat_id"],
                message_id=data["message_id"],
            )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    admin_name = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
    log_event(session, "broadcast", callback.from_user.id, f"{admin_name}: доставлено {sent}, не удалось {failed}")
    await session.commit()

    await callback.message.answer(
        f"✅ Рассылка завершена.\nДоставлено: {sent}\nНе удалось (бот заблокирован и т.п.): {failed}",
        reply_markup=admin_main_menu(),
    )


# ---------- Grant tokens ----------


@router.callback_query(F.data == "adm:granttokens")
async def cb_granttokens_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GrantTokens.waiting_user)
    await callback.message.answer(
        "Кому начислить токены? Пришли Telegram ID пользователя или его @username "
        "(пользователь должен хотя бы раз запускать бота), или /cancel:"
    )
    await callback.answer()


@router.message(GrantTokens.waiting_user)
async def on_granttokens_user(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip().lstrip("@")
    user = None
    if raw.isdigit():
        user = await session.get(User, int(raw))
    else:
        result = await session.execute(select(User).where(User.username == raw))
        user = result.scalar_one_or_none()

    if user is None:
        await message.answer("Не нашёл такого пользователя. Проверь ID/username и попробуй ещё раз, или /cancel:")
        return

    label = f"@{user.username}" if user.username else (user.full_name or str(user.id))
    await state.update_data(target_id=user.id, target_label=label)
    await state.set_state(GrantTokens.waiting_amount)
    await message.answer(
        f"Сколько токенов начислить {label} (сейчас {user.tokens} 🪙)? "
        "Можно отрицательное число, чтобы списать:"
    )


@router.message(GrantTokens.waiting_amount)
async def on_granttokens_amount(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip()
    try:
        amount = int(raw)
    except ValueError:
        await message.answer("Нужно целое число (можно со знаком минус). Попробуй ещё раз:")
        return

    data = await state.get_data()
    user = await session.get(User, data["target_id"])
    await state.clear()
    if user is None:
        await message.answer("Пользователь больше не найден.", reply_markup=admin_main_menu())
        return

    user.tokens = max(0, user.tokens + amount)
    sign = "+" if amount >= 0 else ""
    admin_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    log_event(
        session, "token_grant", message.from_user.id,
        f"{admin_name} начислил(а) {data['target_label']}: {sign}{amount} 🪙 (стало {user.tokens})",
    )
    await session.commit()
    await message.answer(
        f"✅ {data['target_label']}: {sign}{amount} 🪙. Теперь у него {user.tokens} 🪙.",
        reply_markup=admin_main_menu(),
    )


# ---------- Activity log ----------

LOG_PAGE_SIZE = 12


@router.callback_query(F.data.startswith("adm:log:"))
async def cb_activity_log(callback: CallbackQuery, session: AsyncSession) -> None:
    _, _, key, page = callback.data.split(":")
    event_type = None if key == "all" else key
    events, total_pages = await list_events(session, event_type, int(page), LOG_PAGE_SIZE)

    label = "Все события" if event_type is None else EVENT_LABELS.get(event_type, event_type)
    lines = [f"📜 <b>Лог событий</b> ({label})\n"]
    if not events:
        lines.append("Пока пусто.")
    else:
        for e in events:
            ts = e.created_at.strftime("%d.%m %H:%M")
            lines.append(f"{ts} — {e.detail}")

    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=activity_log_kb(event_type, int(page), total_pages)
    )
    await callback.answer()


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

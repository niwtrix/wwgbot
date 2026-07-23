from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Card, Rarity

CARDS_PAGE_SIZE = 8


def admin_main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📇 Карточки участников", callback_data="adm:cards:0")],
        [InlineKeyboardButton(text="🏷 Редкости", callback_data="adm:rarities")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm:settings")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="🆔 Получить ID эмодзи", callback_data="adm:getemoji")],
        [InlineKeyboardButton(text="❓ Справка для админов", callback_data="adm:help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню админки", callback_data="adm:main")]]
    )


def cards_list_kb(cards: list[Card], page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(cards) + CARDS_PAGE_SIZE - 1) // CARDS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = cards[page * CARDS_PAGE_SIZE : (page + 1) * CARDS_PAGE_SIZE]

    rows = []
    for card in chunk:
        status = "" if card.is_active else "🚫 "
        label = f"{status}{card.rarity.emoji_fallback} {card.name}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"adm:card:{card.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:cards:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:cards:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="➕ Добавить участника", callback_data="adm:newcard")])
    rows.append([InlineKeyboardButton(text="🔙 В меню админки", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_edit_menu_kb(card: Card) -> InlineKeyboardMarkup:
    toggle_text = "🚫 Деактивировать" if card.is_active else "✅ Активировать"
    rows = [
        [InlineKeyboardButton(text="✏️ Имя", callback_data=f"adm:cfield:{card.id}:name")],
        [InlineKeyboardButton(text="✏️ Роль/статус", callback_data=f"adm:cfield:{card.id}:role")],
        [InlineKeyboardButton(text="✏️ Цитата", callback_data=f"adm:cfield:{card.id}:quote")],
        [InlineKeyboardButton(text="✏️ Telegram", callback_data=f"adm:cfield:{card.id}:telegram_url")],
        [InlineKeyboardButton(text="✏️ YouTube", callback_data=f"adm:cfield:{card.id}:youtube_url")],
        [InlineKeyboardButton(text="✏️ Twitch", callback_data=f"adm:cfield:{card.id}:twitch_url")],
        [InlineKeyboardButton(text="🖼 Заменить фото", callback_data=f"adm:cphoto:{card.id}")],
        [InlineKeyboardButton(text="🏷 Изменить редкость", callback_data=f"adm:crarity:{card.id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"adm:ctoggle:{card.id}")],
        [InlineKeyboardButton(text="🗑 Удалить карточку", callback_data=f"adm:cdelask:{card.id}")],
        [InlineKeyboardButton(text="🔙 К списку карточек", callback_data="adm:cards:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_card_kb(card_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"adm:cdelyes:{card_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm:card:{card_id}"),
            ]
        ]
    )


def rarity_picker_kb(rarities: list[Rarity], card_id: int) -> InlineKeyboardMarkup:
    rows = []
    for r in rarities:
        rows.append(
            [InlineKeyboardButton(text=f"{r.emoji_fallback} {r.name}", callback_data=f"adm:setrarity:{card_id}:{r.id}")]
        )
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm:card:{card_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rarities_list_kb(rarities: list[Rarity]) -> InlineKeyboardMarkup:
    rows = []
    for r in rarities:
        rows.append(
            [InlineKeyboardButton(text=f"{r.emoji_fallback} {r.name} (вес {r.weight:g})", callback_data=f"adm:rarity:{r.id}")]
        )
    rows.append([InlineKeyboardButton(text="➕ Новая редкость", callback_data="adm:newrarity")])
    rows.append([InlineKeyboardButton(text="🔙 В меню админки", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rarity_edit_menu_kb(rarity: Rarity) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"adm:rfield:{rarity.id}:name")],
        [InlineKeyboardButton(text="✏️ Вес (шанс выпадения)", callback_data=f"adm:rfield:{rarity.id}:weight")],
        [InlineKeyboardButton(text="✏️ Награда токенами", callback_data=f"adm:rfield:{rarity.id}:token_reward")],
        [InlineKeyboardButton(text="✏️ Обычный emoji (запасной)", callback_data=f"adm:rfield:{rarity.id}:emoji_fallback")],
        [InlineKeyboardButton(text="🆔 Премиум emoji ID", callback_data=f"adm:rfield:{rarity.id}:emoji_id")],
        [InlineKeyboardButton(text="🗑 Удалить редкость", callback_data=f"adm:rdelask:{rarity.id}")],
        [InlineKeyboardButton(text="🔙 К списку редкостей", callback_data="adm:rarities")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_rarity_kb(rarity_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"adm:rdelyes:{rarity_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm:rarity:{rarity_id}"),
            ]
        ]
    )


def settings_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="⏱ Кулдаун (минуты)", callback_data="adm:sfield:cooldown_minutes")],
        [InlineKeyboardButton(text="🔁 Бонус токенов за дубль", callback_data="adm:sfield:duplicate_bonus")],
        [InlineKeyboardButton(text="🔙 В меню админки", callback_data="adm:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

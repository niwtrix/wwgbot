from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.activity_repo import EVENT_LABELS, EVENT_TYPES
from app.db.models import Card, Case, Rarity

CARDS_PAGE_SIZE = 8


def admin_main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📇 Карточки участников", callback_data="adm:cardsf:0:all:all")],
        [InlineKeyboardButton(text="🏷 Редкости", callback_data="adm:rarities")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm:settings")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users:0")],
        [InlineKeyboardButton(text="📜 Лог событий", callback_data="adm:log:all:0")],
        [InlineKeyboardButton(text="🪙 Начислить токены", callback_data="adm:granttokens")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="🆔 Получить ID эмодзи", callback_data="adm:getemoji")],
        [InlineKeyboardButton(text="❓ Справка для админов", callback_data="adm:help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню админки", callback_data="adm:main")]]
    )


def cards_list_kb(
    cards: list[Card],
    page: int,
    rarities: list[Rarity] | None = None,
    rarity_filter: str = "all",
    status_filter: str = "all",
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(cards) + CARDS_PAGE_SIZE - 1) // CARDS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = cards[page * CARDS_PAGE_SIZE : (page + 1) * CARDS_PAGE_SIZE]

    rows = []

    if rarities is not None:
        rarity_buttons = [
            InlineKeyboardButton(
                text=("✅ Все" if rarity_filter == "all" else "Все"),
                callback_data=f"adm:cardsf:0:all:{status_filter}",
            )
        ]
        for r in rarities:
            label = f"✅ {r.emoji_fallback}" if rarity_filter == r.id else r.emoji_fallback
            rarity_buttons.append(
                InlineKeyboardButton(text=label, callback_data=f"adm:cardsf:0:{r.id}:{status_filter}")
            )
        for i in range(0, len(rarity_buttons), 4):
            rows.append(rarity_buttons[i : i + 4])

        def _status_btn(value: str, label: str) -> InlineKeyboardButton:
            text = f"✅ {label}" if status_filter == value else label
            return InlineKeyboardButton(text=text, callback_data=f"adm:cardsf:0:{rarity_filter}:{value}")

        rows.append([_status_btn("all", "Все"), _status_btn("active", "Активные"), _status_btn("inactive", "Выкл.")])

    for card in chunk:
        status = "" if card.is_active else "🚫 "
        label = f"{status}{card.rarity.emoji_fallback} {card.name}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"adm:card:{card.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:cardsf:{page - 1}:{rarity_filter}:{status_filter}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:cardsf:{page + 1}:{rarity_filter}:{status_filter}"))
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
        [InlineKeyboardButton(text="🔙 К списку карточек", callback_data="adm:cardsf:0:all:all")],
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
    case_only_text = "🎁 Только из кейсов: ВКЛ (тап — выключить)" if rarity.case_only else "🎁 Только из кейсов: ВЫКЛ (тап — включить)"
    rows = [
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"adm:rfield:{rarity.id}:name")],
        [InlineKeyboardButton(text="✏️ Вес (шанс выпадения)", callback_data=f"adm:rfield:{rarity.id}:weight")],
        [InlineKeyboardButton(text="✏️ Награда токенами", callback_data=f"adm:rfield:{rarity.id}:token_reward")],
        [InlineKeyboardButton(text="✏️ Ценность для /upgrade", callback_data=f"adm:rfield:{rarity.id}:upgrade_value")],
        [InlineKeyboardButton(text="✏️ Обычный emoji (запасной)", callback_data=f"adm:rfield:{rarity.id}:emoji_fallback")],
        [InlineKeyboardButton(text="🆔 Премиум emoji ID", callback_data=f"adm:rfield:{rarity.id}:emoji_id")],
        [InlineKeyboardButton(text=case_only_text, callback_data=f"adm:rtogglecaseonly:{rarity.id}")],
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


def cases_list_kb(cases: list[Case]) -> InlineKeyboardMarkup:
    rows = []
    for c in cases:
        status = "" if c.is_active else "🚫 "
        rows.append(
            [InlineKeyboardButton(text=f"{status}🎁 {c.name} ({c.price_tokens} 🪙)", callback_data=f"adm:case:{c.id}")]
        )
    rows.append([InlineKeyboardButton(text="➕ Новый кейс", callback_data="adm:newcase")])
    rows.append([InlineKeyboardButton(text="🔙 К настройкам", callback_data="adm:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def case_edit_menu_kb(case: Case) -> InlineKeyboardMarkup:
    toggle_text = "🚫 Деактивировать" if case.is_active else "✅ Активировать"
    rows = [
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"adm:cafield:{case.id}:name")],
        [InlineKeyboardButton(text="✏️ Цена (токены)", callback_data=f"adm:cafield:{case.id}:price_tokens")],
        [InlineKeyboardButton(text="✏️ Описание", callback_data=f"adm:cafield:{case.id}:description")],
        [InlineKeyboardButton(text="🎲 Содержимое (шансы по редкости)", callback_data=f"adm:caodds:{case.id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"adm:catoggle:{case.id}")],
        [InlineKeyboardButton(text="🗑 Удалить кейс", callback_data=f"adm:cadelask:{case.id}")],
        [InlineKeyboardButton(text="🔙 К списку кейсов", callback_data="adm:cases")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_case_kb(case_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"adm:cadelyes:{case_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm:case:{case_id}"),
            ]
        ]
    )


def case_odds_kb(
    case: Case,
    cards: list[Card],
    page: int,
    rarity_filter: str,
    rarities: list[Rarity],
) -> InlineKeyboardMarkup:
    odds_by_card = {o.card_id: o.weight for o in case.card_odds}

    total_pages = max(1, (len(cards) + CARDS_PAGE_SIZE - 1) // CARDS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = cards[page * CARDS_PAGE_SIZE : (page + 1) * CARDS_PAGE_SIZE]

    rows = []

    rarity_row = [
        InlineKeyboardButton(
            text=("✅ Все" if rarity_filter == "all" else "Все"), callback_data=f"adm:caodds:{case.id}:0:all"
        )
    ]
    for r in rarities:
        label = f"✅ {r.emoji_fallback}" if rarity_filter == r.id else r.emoji_fallback
        rarity_row.append(InlineKeyboardButton(text=label, callback_data=f"adm:caodds:{case.id}:0:{r.id}"))
    for i in range(0, len(rarity_row), 4):
        rows.append(rarity_row[i : i + 4])

    for card in chunk:
        weight = odds_by_card.get(card.id)
        label = f"{card.rarity.emoji_fallback} {card.name}: {weight:g}" if weight else f"{card.rarity.emoji_fallback} {card.name}: —"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"adm:caoddsset:{case.id}:{card.id}:{page}:{rarity_filter}")]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:caodds:{case.id}:{page - 1}:{rarity_filter}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:caodds:{case.id}:{page + 1}:{rarity_filter}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm:case:{case.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def activity_log_kb(event_type: str | None, page: int, total_pages: int) -> InlineKeyboardMarkup:
    all_label = "✅ Все" if event_type is None else "Все"
    rows = [[InlineKeyboardButton(text=all_label, callback_data="adm:log:all:0")]]

    filter_row = []
    for et in EVENT_TYPES:
        label = EVENT_LABELS[et]
        if event_type == et:
            label = "✅ " + label
        filter_row.append(InlineKeyboardButton(text=label, callback_data=f"adm:log:{et}:0"))
        if len(filter_row) == 2:
            rows.append(filter_row)
            filter_row = []
    if filter_row:
        rows.append(filter_row)

    key = event_type or "all"
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:log:{key}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{max(total_pages, 1)}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:log:{key}:{page + 1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 В меню админки", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_list_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm:users:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{max(total_pages, 1)}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm:users:{page + 1}"))
    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton(text="🔙 В меню админки", callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить всем", callback_data="adm:broadcastsend"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="adm:broadcastcancel"),
            ]
        ]
    )


def settings_menu_kb(health_report_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔕 Выключить отчёты о статусе" if health_report_enabled else "🔔 Включить отчёты о статусе"
    rows = [
        [InlineKeyboardButton(text="⏱ Кулдаун (минуты)", callback_data="adm:sfield:cooldown_minutes")],
        [InlineKeyboardButton(text="🔁 Бонус токенов за дубль", callback_data="adm:sfield:duplicate_bonus")],
        [InlineKeyboardButton(text="💰 Цена доп. ролла (токены)", callback_data="adm:sfield:extra_roll_price")],
        [InlineKeyboardButton(text="🛡 Защита от дублей: мин. пуллов", callback_data="adm:sfield:pity_floor_pulls")],
        [InlineKeyboardButton(text="🛡 Защита от дублей: пуллов на восстановление", callback_data="adm:sfield:pity_ramp_pulls")],
        [InlineKeyboardButton(text="🛡 Защита от дублей: мин. доля шанса", callback_data="adm:sfield:pity_min_weight_fraction")],
        [InlineKeyboardButton(text=toggle_text, callback_data="adm:togglehealthreport")],
        [InlineKeyboardButton(text="⏱ Интервал отчётов (минуты)", callback_data="adm:sfield:health_report_interval_minutes")],
        [InlineKeyboardButton(text="✏️ Текст /start", callback_data="adm:sfield:start_text")],
        [InlineKeyboardButton(text="✏️ Текст /help", callback_data="adm:sfield:help_text")],
        [InlineKeyboardButton(text="🔗 Бонус за реферала", callback_data="adm:sfield:referral_bonus_tokens")],
        [InlineKeyboardButton(text="📅 Ежедн. бонус: база", callback_data="adm:sfield:daily_bonus_base_tokens")],
        [InlineKeyboardButton(text="📅 Ежедн. бонус: прирост за серию", callback_data="adm:sfield:daily_bonus_streak_step")],
        [InlineKeyboardButton(text="📅 Ежедн. бонус: максимум", callback_data="adm:sfield:daily_bonus_max_tokens")],
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="adm:cases")],
        [InlineKeyboardButton(text="🔙 В меню админки", callback_data="adm:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

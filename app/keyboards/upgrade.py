from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Card, Rarity

PICKER_PAGE_SIZE = 8


def upgrade_room_kb(can_add: bool, can_remove: bool, can_spin: bool) -> InlineKeyboardMarkup:
    rows = []
    action_row = []
    if can_add:
        action_row.append(InlineKeyboardButton(text="➕ Добавить в ставку", callback_data="upg:add:0"))
    if can_remove:
        action_row.append(InlineKeyboardButton(text="➖ Убрать из ставки", callback_data="upg:remove:0"))
    if action_row:
        rows.append(action_row)
    rows.append([InlineKeyboardButton(text="🎯 Выбрать цель", callback_data="upg:target:0:all")])
    if can_spin:
        rows.append([InlineKeyboardButton(text="🎲 Крутить!", callback_data="upg:spin")])
    rows.append([InlineKeyboardButton(text="❌ Отменить", callback_data="upg:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upgrade_add_picker_kb(cards_with_avail: list[tuple[Card, int]], page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(cards_with_avail) + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = cards_with_avail[page * PICKER_PAGE_SIZE : (page + 1) * PICKER_PAGE_SIZE]

    rows = []
    for card, avail in chunk:
        label = f"{card.rarity.emoji_fallback} {card.name} (est. {card.rarity.token_reward:g}, доступно {avail})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"upg:additem:{card.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"upg:add:{page - 1}"))
    if cards_with_avail:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"upg:add:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="upg:room")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upgrade_remove_picker_kb(items: list[tuple[Card, int]], page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(items) + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * PICKER_PAGE_SIZE : (page + 1) * PICKER_PAGE_SIZE]

    rows = []
    for card, qty in chunk:
        label = f"{card.rarity.emoji_fallback} {card.name} ×{qty}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"upg:removeitem:{card.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"upg:remove:{page - 1}"))
    if items:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"upg:remove:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="upg:room")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upgrade_target_picker_kb(
    cards: list[Card], page: int, rarity_filter: str, rarities: list[Rarity]
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(cards) + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = cards[page * PICKER_PAGE_SIZE : (page + 1) * PICKER_PAGE_SIZE]

    rows = []

    rarity_row = [
        InlineKeyboardButton(
            text=("✅ Все" if rarity_filter == "all" else "Все"), callback_data="upg:target:0:all"
        )
    ]
    for r in rarities:
        label = f"✅ {r.emoji_fallback}" if rarity_filter == r.id else r.emoji_fallback
        rarity_row.append(InlineKeyboardButton(text=label, callback_data=f"upg:target:0:{r.id}"))
    for i in range(0, len(rarity_row), 4):
        rows.append(rarity_row[i : i + 4])

    for card in chunk:
        label = f"{card.rarity.emoji_fallback} {card.name} (est. {card.rarity.token_reward:g})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"upg:settarget:{card.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"upg:target:{page - 1}:{rarity_filter}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"upg:target:{page + 1}:{rarity_filter}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="upg:room")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

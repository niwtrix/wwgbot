from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Card, TradeItem

PICKER_PAGE_SIZE = 8


def trade_invite_kb(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"trade:accept:{trade_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"trade:decline:{trade_id}"),
            ]
        ]
    )


def trade_pending_kb(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить предложение", callback_data=f"trade:decline:{trade_id}")]]
    )


def trade_room_kb(trade_id: int, my_ready: bool) -> InlineKeyboardMarkup:
    ready_text = "⏳ Отменить готовность" if my_ready else "✅ Готов(а) к обмену"
    rows = []
    if not my_ready:
        rows.append(
            [
                InlineKeyboardButton(text="➕ Добавить карточку", callback_data=f"trade:add:{trade_id}:0"),
                InlineKeyboardButton(text="➖ Убрать карточку", callback_data=f"trade:remove:{trade_id}:0"),
            ]
        )
    rows.append([InlineKeyboardButton(text=ready_text, callback_data=f"trade:ready:{trade_id}")])
    rows.append([InlineKeyboardButton(text="❌ Отменить трейд", callback_data=f"trade:cancel:{trade_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_confirm_kb(trade_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить обмен", callback_data=f"trade:confirm:{trade_id}"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"trade:cancel:{trade_id}"),
            ]
        ]
    )


def trade_add_picker_kb(trade_id: int, cards: list[tuple[Card, int]], page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(cards) + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = cards[page * PICKER_PAGE_SIZE : (page + 1) * PICKER_PAGE_SIZE]

    rows = []
    for card, available in chunk:
        label = f"{card.rarity.emoji_fallback} {card.name} (доступно {available})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"trade:additem:{trade_id}:{card.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"trade:add:{trade_id}:{page - 1}"))
    if cards:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"trade:add:{trade_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Назад к трейду", callback_data=f"trade:room:{trade_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_remove_picker_kb(trade_id: int, items: list[TradeItem], page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(items) + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * PICKER_PAGE_SIZE : (page + 1) * PICKER_PAGE_SIZE]

    rows = []
    for item in chunk:
        label = f"{item.card.rarity.emoji_fallback} {item.card.name} ×{item.qty}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"trade:removeitem:{trade_id}:{item.card_id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"trade:remove:{trade_id}:{page - 1}"))
    if items:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"trade:remove:{trade_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Назад к трейду", callback_data=f"trade:room:{trade_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

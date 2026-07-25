from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Card, Case


def buy_roll_kb(price: int, affordable: bool) -> InlineKeyboardMarkup:
    text = f"💰 Купить доп. ролл ({price} 🪙)" if affordable else f"💰 Купить доп. ролл ({price} 🪙) — не хватает токенов"
    rows = [[InlineKeyboardButton(text=text, callback_data="buyroll" if affordable else "noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cases_list_kb(cases: list[Case], user_tokens: int) -> InlineKeyboardMarkup:
    rows = []
    for c in cases:
        affordable = user_tokens >= c.price_tokens
        text = f"🎁 {c.name} — {c.price_tokens} 🪙" if affordable else f"🎁 {c.name} — {c.price_tokens} 🪙 (не хватает)"
        rows.append(
            [InlineKeyboardButton(text=text, callback_data=f"opencase:{c.id}" if affordable else "noop")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_links_kb(card: Card) -> InlineKeyboardMarkup | None:
    buttons = []
    if card.telegram_url:
        buttons.append(InlineKeyboardButton(text="💬 Telegram", url=card.telegram_url))
    if card.youtube_url:
        buttons.append(InlineKeyboardButton(text="📺 YouTube", url=card.youtube_url))
    if card.twitch_url:
        buttons.append(InlineKeyboardButton(text="🎮 Twitch", url=card.twitch_url))

    if not buttons:
        return None

    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def top_kb(mode: str) -> InlineKeyboardMarkup:
    tokens_text = "✅ 🪙 По токенам" if mode == "tokens" else "🪙 По токенам"
    cards_text = "✅ 🎴 По карточкам" if mode == "cards" else "🎴 По карточкам"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=tokens_text, callback_data="top:tokens"),
                InlineKeyboardButton(text=cards_text, callback_data="top:cards"),
            ]
        ]
    )


def profile_kb(hide_from_top: bool) -> InlineKeyboardMarkup:
    text = "👁 Показывать себя в /top" if hide_from_top else "🙈 Скрыть себя из /top"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="toggletop")]])


def mycards_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🖼 Смотреть как карточки", callback_data="mygallery:0")]]

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"mycards:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"mycards:{page + 1}"))
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def mycards_gallery_kb(index: int, total: int, card: Card) -> InlineKeyboardMarkup:
    rows = []
    links = card_links_kb(card)
    if links:
        rows.extend(links.inline_keyboard)

    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"mygallery:{index - 1}"))
    nav.append(InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop"))
    if index < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"mygallery:{index + 1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton(text="📋 К списку", callback_data="mygallery:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

from html import escape

from app.db.models import Card, Rarity

# custom_emoji_id for the platform icons, found via /getemojiid
PLATFORM_EMOJI = {
    "telegram": ("💬", "5285350148451344065"),
    "youtube": ("📺", "5278611117130653414"),
    "twitch": ("🎮", "5303434898525136153"),
}


def tg_emoji(fallback: str, emoji_id: str | None) -> str:
    if emoji_id:
        return f'<tg-emoji emoji-id="{escape(emoji_id)}">{fallback}</tg-emoji>'
    return fallback


def rarity_html(rarity: Rarity) -> str:
    """Render a rarity's icon as an HTML tg-emoji tag (falls back to a plain unicode emoji
    automatically on clients/cards that don't resolve the custom_emoji_id)."""
    return tg_emoji(rarity.emoji_fallback, rarity.emoji_id)


def platform_icons_line(card: Card) -> str:
    icons = []
    if card.telegram_url:
        icons.append(tg_emoji(*PLATFORM_EMOJI["telegram"]))
    if card.youtube_url:
        icons.append(tg_emoji(*PLATFORM_EMOJI["youtube"]))
    if card.twitch_url:
        icons.append(tg_emoji(*PLATFORM_EMOJI["twitch"]))
    return " ".join(icons)


def card_caption(card: Card, *, extra: str = "") -> str:
    lines = [f"<b>{escape(card.name)}</b>"]
    if card.role:
        lines.append(escape(card.role))
    lines.append("")
    if card.quote:
        lines.append(f"<i>{escape(card.quote)}</i>")
        lines.append("")
    lines.append(f"{rarity_html(card.rarity)} {escape(card.rarity.name)}")
    if extra:
        lines.append("")
        lines.append(extra)
    return "\n".join(lines)

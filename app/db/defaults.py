DEFAULT_RARITIES = [
    # id, name, weight, token_reward, emoji_fallback, sort_order
    ("common", "Обычная", 40.0, 5, "⚪", 0),
    ("rare", "Редкая", 30.0, 10, "🔹", 1),
    ("very_rare", "Очень редкая", 15.0, 20, "🔷", 2),
    ("epic", "Эпическая", 8.0, 35, "💎", 3),
    ("legendary", "Легендарная", 5.0, 60, "🌟", 4),
    ("mythic", "Мифическая", 2.0, 100, "👑", 5),
]

DEFAULT_SETTINGS = {
    "cooldown_minutes": "120",
    "duplicate_bonus": "10",
}

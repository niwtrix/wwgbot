DEFAULT_RARITIES = [
    # id, name, weight, token_reward, emoji_fallback, sort_order, case_only
    ("rare", "Редкая", 25.0, 15, "🔹", 0, False),
    ("very_rare", "Сверхредкая", 30.0, 20, "🔷", 1, False),
    ("epic", "Эпическая", 20.0, 25, "💎", 2, False),
    ("mythic", "Мифическая", 15.0, 40, "👑", 3, False),
    ("legendary", "Легендарная", 10.0, 70, "🌟", 4, False),
    ("chromatic", "Хроматическая", 0.0, 0, "✨", 5, True),
]

DEFAULT_SETTINGS = {
    "cooldown_minutes": "120",
    "duplicate_bonus": "10",
    "extra_roll_price": "45",
    "pity_floor_pulls": "5",
    "pity_ramp_pulls": "10",
    "pity_min_weight_fraction": "0.1",
    "health_report_enabled": "1",
    "health_report_interval_minutes": "5",
}

DEFAULT_CASES = [
    # slug, name, price_tokens, description, sort_order, odds: [(rarity_id, weight), ...]
    (
        "chromatic",
        "Хроматический кейс",
        100,
        "Гарантированная хроматическая карточка",
        0,
        [("chromatic", 100.0)],
    ),
]

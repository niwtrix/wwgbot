import random
from collections import defaultdict

from app.db.models import Card


def weighted_draw(cards: list[Card]) -> Card | None:
    """Pick a rarity tier by weight, then a uniformly random card within it."""
    if not cards:
        return None

    by_rarity: dict[str, list[Card]] = defaultdict(list)
    for card in cards:
        by_rarity[card.rarity_id].append(card)

    tiers = []  # (rarity_weight, cards_in_tier)
    total_weight = 0.0
    for rarity_id, tier_cards in by_rarity.items():
        weight = tier_cards[0].rarity.weight
        total_weight += weight
        tiers.append((weight, tier_cards))

    if total_weight <= 0:
        return random.choice(cards)

    roll = random.uniform(0, total_weight)
    upto = 0.0
    for weight, tier_cards in tiers:
        upto += weight
        if roll <= upto:
            return random.choice(tier_cards)

    return random.choice(tiers[-1][1])

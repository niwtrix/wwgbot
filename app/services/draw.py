import random
from collections import defaultdict

from app.db.models import Card, UserCard


def _pity_multiplier(user_card: UserCard | None, floor: int, ramp: int, min_fraction: float) -> float:
    """1.0 for cards the user doesn't own yet. For owned cards: 0 (fully blocked) for the
    first `floor` pulls since they were obtained, then ramps linearly from `min_fraction`
    back up to 1.0 over the next `ramp` pulls."""
    if user_card is None:
        return 1.0
    pulls = user_card.pulls_since_obtained
    if pulls < floor:
        return 0.0
    if ramp <= 0 or pulls >= floor + ramp:
        return 1.0
    progress = (pulls - floor) / ramp
    return min_fraction + (1.0 - min_fraction) * progress


def _pick_from_tier(
    tier_cards: list[Card],
    owned: dict[int, UserCard],
    pity_floor: int,
    pity_ramp: int,
    pity_min_fraction: float,
) -> Card | None:
    weights = [
        _pity_multiplier(owned.get(c.id), pity_floor, pity_ramp, pity_min_fraction) for c in tier_cards
    ]
    total = sum(weights)
    if total <= 0:
        return None
    roll = random.uniform(0, total)
    acc = 0.0
    for card, w in zip(tier_cards, weights):
        acc += w
        if roll <= acc:
            return card
    return tier_cards[-1]


def weighted_draw(
    cards: list[Card],
    owned: dict[int, UserCard] | None = None,
    pity_floor: int = 5,
    pity_ramp: int = 10,
    pity_min_fraction: float = 0.1,
    rarity_weights: dict[str, float] | None = None,
) -> Card | None:
    """Pick a rarity tier by weight, then a card within it — weighted by a duplicate-pity
    multiplier so a just-obtained card can't repeat for `pity_floor` pulls and gradually
    regains normal odds over the following `pity_ramp` pulls.

    By default tier weight comes from each rarity's own `.weight`. Pass `rarity_weights`
    (rarity_id -> weight) to override with a custom distribution instead (e.g. a case's
    own odds table)."""
    if not cards:
        return None

    owned = owned or {}

    by_rarity: dict[str, list[Card]] = defaultdict(list)
    for card in cards:
        by_rarity[card.rarity_id].append(card)

    tiers: list[tuple[float, list[Card]]] = []
    total_weight = 0.0
    for rarity_id, tier_cards in by_rarity.items():
        weight = rarity_weights[rarity_id] if rarity_weights is not None else tier_cards[0].rarity.weight
        if weight <= 0:
            continue
        total_weight += weight
        tiers.append((weight, tier_cards))

    if not tiers:
        return random.choice(cards)

    roll = random.uniform(0, total_weight)
    upto = 0.0
    chosen_tier = tiers[-1][1]
    for weight, tier_cards in tiers:
        upto += weight
        if roll <= upto:
            chosen_tier = tier_cards
            break

    result = _pick_from_tier(chosen_tier, owned, pity_floor, pity_ramp, pity_min_fraction)
    if result is not None:
        return result

    # chosen tier fully pity-blocked (user owns every card in it, all obtained recently) —
    # try the other tiers before giving up
    other_tiers = [t for _, t in tiers if t is not chosen_tier]
    random.shuffle(other_tiers)
    for tier_cards in other_tiers:
        result = _pick_from_tier(tier_cards, owned, pity_floor, pity_ramp, pity_min_fraction)
        if result is not None:
            return result

    # last resort: ignore pity entirely rather than fail the pull
    return random.choice(cards)


def weighted_draw_by_card(
    cards: list[Card],
    card_weights: dict[int, float],
    owned: dict[int, UserCard] | None = None,
    pity_floor: int = 5,
    pity_ramp: int = 10,
    pity_min_fraction: float = 0.1,
) -> Card | None:
    """Direct single-level weighted draw across specific cards (e.g. a case's own per-card
    odds table), still respecting the duplicate-pity multiplier per card."""
    if not cards:
        return None

    owned = owned or {}

    weights = [
        card_weights.get(c.id, 0.0) * _pity_multiplier(owned.get(c.id), pity_floor, pity_ramp, pity_min_fraction)
        for c in cards
    ]
    total = sum(weights)

    if total <= 0:
        # everything pity-blocked (or zero-weighted) — fall back to ignoring pity
        weights = [card_weights.get(c.id, 0.0) for c in cards]
        total = sum(weights)
        if total <= 0:
            return None

    roll = random.uniform(0, total)
    acc = 0.0
    for card, w in zip(cards, weights):
        acc += w
        if roll <= acc:
            return card
    return cards[-1]

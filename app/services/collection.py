from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.cards_repo import list_active_cards
from app.db.models import Card, Case, User, UserCard
from app.db.settings_repo import get_setting, get_setting_int
from app.services.draw import weighted_draw


@dataclass
class PullResult:
    card: Card
    is_duplicate: bool
    copies_owned: int
    tokens_awarded: int


async def _get_owned_map(session: AsyncSession, user_id: int) -> dict[int, UserCard]:
    result = await session.execute(select(UserCard).where(UserCard.user_id == user_id))
    return {uc.card_id: uc for uc in result.scalars().all()}


async def _get_pity_settings(session: AsyncSession) -> tuple[int, int, float]:
    floor = await get_setting_int(session, "pity_floor_pulls")
    ramp = await get_setting_int(session, "pity_ramp_pulls")
    min_fraction = float(await get_setting(session, "pity_min_weight_fraction"))
    return floor, ramp, min_fraction


async def _apply_pull(session: AsyncSession, user: User, card: Card, owned: dict[int, UserCard]) -> PullResult:
    now = datetime.now(timezone.utc)

    for uc in owned.values():
        uc.pulls_since_obtained += 1

    user_card = owned.get(card.id)
    is_duplicate = user_card is not None
    if user_card is None:
        user_card = UserCard(
            user_id=user.id, card_id=card.id, count=1, first_obtained_at=now, last_obtained_at=now,
            pulls_since_obtained=0,
        )
        session.add(user_card)
    else:
        user_card.count += 1
        user_card.last_obtained_at = now
        user_card.pulls_since_obtained = 0

    tokens_awarded = card.rarity.token_reward
    if is_duplicate:
        tokens_awarded += await get_setting_int(session, "duplicate_bonus")

    user.tokens += tokens_awarded

    return PullResult(card=card, is_duplicate=is_duplicate, copies_owned=user_card.count, tokens_awarded=tokens_awarded)


async def pull_card(session: AsyncSession, user: User) -> PullResult | None:
    """Free, cooldown-gated pull. Caller must check the cooldown before calling this."""
    cards = [c for c in await list_active_cards(session) if not c.rarity.case_only]
    owned = await _get_owned_map(session, user.id)
    floor, ramp, min_fraction = await _get_pity_settings(session)

    card = weighted_draw(cards, owned, floor, ramp, min_fraction)
    if card is None:
        return None

    result = await _apply_pull(session, user, card, owned)
    user.last_pull_at = datetime.now(timezone.utc)
    await session.commit()
    return result


async def buy_extra_roll(session: AsyncSession, user: User) -> tuple[PullResult, int] | None:
    """Purchased roll: costs tokens, independent of the free cooldown timer.
    Returns (result, price_paid), or None if the user can't afford it or there's no card
    to draw."""
    price = await get_setting_int(session, "extra_roll_price")
    if user.tokens < price:
        return None

    cards = [c for c in await list_active_cards(session) if not c.rarity.case_only]
    owned = await _get_owned_map(session, user.id)
    floor, ramp, min_fraction = await _get_pity_settings(session)

    card = weighted_draw(cards, owned, floor, ramp, min_fraction)
    if card is None:
        return None

    user.tokens -= price
    result = await _apply_pull(session, user, card, owned)
    await session.commit()
    return result, price


async def open_case(session: AsyncSession, user: User, case: Case) -> PullResult | None:
    """Open a case: costs case.price_tokens, draws from the case's own rarity odds table
    (independent of the normal roll weights). Returns None if unaffordable or the case
    has no eligible cards right now."""
    if user.tokens < case.price_tokens:
        return None

    rarity_weights = {o.rarity_id: o.weight for o in case.odds if o.weight > 0}
    if not rarity_weights:
        return None

    all_cards = await list_active_cards(session)
    cards = [c for c in all_cards if c.rarity_id in rarity_weights]
    if not cards:
        return None

    owned = await _get_owned_map(session, user.id)
    floor, ramp, min_fraction = await _get_pity_settings(session)

    card = weighted_draw(cards, owned, floor, ramp, min_fraction, rarity_weights=rarity_weights)
    if card is None:
        return None

    user.tokens -= case.price_tokens
    result = await _apply_pull(session, user, card, owned)
    await session.commit()
    return result

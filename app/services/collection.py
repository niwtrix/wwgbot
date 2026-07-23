from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.cards_repo import list_active_cards
from app.db.models import Card, User, UserCard
from app.db.settings_repo import get_setting_int
from app.services.draw import weighted_draw


@dataclass
class PullResult:
    card: Card
    is_duplicate: bool
    copies_owned: int
    tokens_awarded: int


async def pull_card(session: AsyncSession, user: User) -> PullResult | None:
    cards = await list_active_cards(session)
    card = weighted_draw(cards)
    if card is None:
        return None

    user_card = await session.get(UserCard, (user.id, card.id))
    is_duplicate = user_card is not None

    now = datetime.now(timezone.utc)
    if user_card is None:
        user_card = UserCard(user_id=user.id, card_id=card.id, count=1, first_obtained_at=now, last_obtained_at=now)
        session.add(user_card)
    else:
        user_card.count += 1
        user_card.last_obtained_at = now

    tokens_awarded = card.rarity.token_reward
    if is_duplicate:
        tokens_awarded += await get_setting_int(session, "duplicate_bonus")

    user.tokens += tokens_awarded
    user.last_pull_at = now

    await session.commit()

    return PullResult(
        card=card,
        is_duplicate=is_duplicate,
        copies_owned=user_card.count,
        tokens_awarded=tokens_awarded,
    )

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Card, Case, CaseCardOdds, Rarity


async def list_cases(session: AsyncSession) -> list[Case]:
    result = await session.execute(
        select(Case)
        .options(selectinload(Case.card_odds).selectinload(CaseCardOdds.card).selectinload(Card.rarity))
        .order_by(Case.sort_order)
    )
    return list(result.scalars().all())


async def list_active_cases(session: AsyncSession) -> list[Case]:
    result = await session.execute(
        select(Case)
        .where(Case.is_active.is_(True))
        .options(selectinload(Case.card_odds).selectinload(CaseCardOdds.card).selectinload(Card.rarity))
        .order_by(Case.sort_order)
    )
    return list(result.scalars().all())


async def get_case(session: AsyncSession, case_id: int) -> Case | None:
    result = await session.execute(
        select(Case)
        .where(Case.id == case_id)
        .options(selectinload(Case.card_odds).selectinload(CaseCardOdds.card).selectinload(Card.rarity))
    )
    return result.scalar_one_or_none()


async def set_case_card_odds(session: AsyncSession, case_id: int, card_id: int, weight: float) -> None:
    result = await session.execute(
        select(CaseCardOdds).where(CaseCardOdds.case_id == case_id, CaseCardOdds.card_id == card_id)
    )
    existing = result.scalar_one_or_none()
    if weight <= 0:
        if existing:
            await session.delete(existing)
    elif existing:
        existing.weight = weight
    else:
        session.add(CaseCardOdds(case_id=case_id, card_id=card_id, weight=weight))
    await session.commit()


def case_rarity_summary(case: Case) -> list[Rarity]:
    """Distinct rarities represented among a case's included cards, in rarity sort order —
    used for user-facing display without listing every individual card."""
    seen: dict[str, Rarity] = {}
    for o in case.card_odds:
        if o.weight > 0:
            seen[o.card.rarity_id] = o.card.rarity
    return sorted(seen.values(), key=lambda r: r.sort_order)

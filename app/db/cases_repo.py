from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Case, CaseOdds


async def list_cases(session: AsyncSession) -> list[Case]:
    result = await session.execute(
        select(Case).options(selectinload(Case.odds).selectinload(CaseOdds.rarity)).order_by(Case.sort_order)
    )
    return list(result.scalars().all())


async def list_active_cases(session: AsyncSession) -> list[Case]:
    result = await session.execute(
        select(Case)
        .where(Case.is_active.is_(True))
        .options(selectinload(Case.odds).selectinload(CaseOdds.rarity))
        .order_by(Case.sort_order)
    )
    return list(result.scalars().all())


async def get_case(session: AsyncSession, case_id: int) -> Case | None:
    result = await session.execute(
        select(Case)
        .where(Case.id == case_id)
        .options(selectinload(Case.odds).selectinload(CaseOdds.rarity))
    )
    return result.scalar_one_or_none()


async def set_case_odds(session: AsyncSession, case_id: int, rarity_id: str, weight: float) -> None:
    result = await session.execute(
        select(CaseOdds).where(CaseOdds.case_id == case_id, CaseOdds.rarity_id == rarity_id)
    )
    existing = result.scalar_one_or_none()
    if weight <= 0:
        if existing:
            await session.delete(existing)
    elif existing:
        existing.weight = weight
    else:
        session.add(CaseOdds(case_id=case_id, rarity_id=rarity_id, weight=weight))
    await session.commit()

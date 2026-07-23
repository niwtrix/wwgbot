from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Card, Rarity


async def list_active_cards(session: AsyncSession) -> list[Card]:
    result = await session.execute(
        select(Card).where(Card.is_active.is_(True)).options(selectinload(Card.rarity))
    )
    return list(result.scalars().all())


async def list_all_cards(session: AsyncSession) -> list[Card]:
    result = await session.execute(
        select(Card).options(selectinload(Card.rarity)).order_by(Card.name)
    )
    return list(result.scalars().all())


async def get_card(session: AsyncSession, card_id: int) -> Card | None:
    result = await session.execute(
        select(Card).where(Card.id == card_id).options(selectinload(Card.rarity))
    )
    return result.scalar_one_or_none()


async def get_card_by_slug(session: AsyncSession, slug: str) -> Card | None:
    result = await session.execute(
        select(Card).where(Card.slug == slug).options(selectinload(Card.rarity))
    )
    return result.scalar_one_or_none()


async def find_card_by_query(session: AsyncSession, query: str) -> Card | None:
    """Look up a card by exact slug, or case-insensitive name/slug match."""
    result = await session.execute(
        select(Card)
        .where(func.lower(Card.slug) == query.lower())
        .options(selectinload(Card.rarity))
    )
    card = result.scalar_one_or_none()
    if card:
        return card

    result = await session.execute(
        select(Card)
        .where(func.lower(Card.name) == query.lower())
        .options(selectinload(Card.rarity))
    )
    return result.scalar_one_or_none()


async def list_rarities(session: AsyncSession) -> list[Rarity]:
    result = await session.execute(select(Rarity).order_by(Rarity.sort_order))
    return list(result.scalars().all())


async def get_rarity(session: AsyncSession, rarity_id: str) -> Rarity | None:
    return await session.get(Rarity, rarity_id)

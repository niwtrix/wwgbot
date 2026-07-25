from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Card, Trade, TradeItem, User, UserCard

ACTIVE_STATUSES = ("pending", "active", "confirming")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_active_trade_for_user(session: AsyncSession, user_id: int) -> Trade | None:
    result = await session.execute(
        select(Trade)
        .where(
            Trade.status.in_(ACTIVE_STATUSES),
            (Trade.initiator_id == user_id) | (Trade.counterparty_id == user_id),
        )
        .options(
            selectinload(Trade.items).selectinload(TradeItem.card).selectinload(Card.rarity),
            selectinload(Trade.initiator),
            selectinload(Trade.counterparty),
        )
    )
    return result.scalar_one_or_none()


async def get_trade(session: AsyncSession, trade_id: int) -> Trade | None:
    result = await session.execute(
        select(Trade)
        .where(Trade.id == trade_id)
        .options(
            selectinload(Trade.items).selectinload(TradeItem.card).selectinload(Card.rarity),
            selectinload(Trade.initiator),
            selectinload(Trade.counterparty),
        )
    )
    return result.scalar_one_or_none()


async def create_trade(session: AsyncSession, initiator_id: int, counterparty_id: int) -> Trade:
    trade = Trade(initiator_id=initiator_id, counterparty_id=counterparty_id, status="pending")
    session.add(trade)
    await session.commit()
    return await get_trade(session, trade.id)


async def owned_qty(session: AsyncSession, user_id: int, card_id: int) -> int:
    uc = await session.get(UserCard, (user_id, card_id))
    return uc.count if uc else 0


async def offered_qty(trade: Trade, user_id: int, card_id: int) -> int:
    return sum(i.qty for i in trade.items if i.offered_by_id == user_id and i.card_id == card_id)


async def addable_cards(session: AsyncSession, trade: Trade, user_id: int) -> list[tuple[Card, int]]:
    """Cards this user owns that still have copies not yet offered in this trade."""
    result = await session.execute(
        select(UserCard)
        .where(UserCard.user_id == user_id, UserCard.count > 0)
        .options(selectinload(UserCard.card).selectinload(Card.rarity))
        .join(Card)
        .order_by(Card.name)
    )
    owned = list(result.scalars().all())
    out = []
    for uc in owned:
        already = await offered_qty(trade, user_id, uc.card_id)
        available = uc.count - already
        if available > 0:
            out.append((uc.card, available))
    return out


def offered_items_by(trade: Trade, user_id: int) -> list[TradeItem]:
    return [i for i in trade.items if i.offered_by_id == user_id]


async def add_item(session: AsyncSession, trade: Trade, user_id: int, card_id: int) -> bool:
    owned = await owned_qty(session, user_id, card_id)
    already = await offered_qty(trade, user_id, card_id)
    if already >= owned:
        return False

    for item in trade.items:
        if item.offered_by_id == user_id and item.card_id == card_id:
            item.qty += 1
            break
    else:
        session.add(TradeItem(trade_id=trade.id, offered_by_id=user_id, card_id=card_id, qty=1))

    trade.ready_initiator = False
    trade.ready_counterparty = False
    await session.commit()
    return True


async def remove_item(session: AsyncSession, trade: Trade, user_id: int, card_id: int) -> bool:
    for item in trade.items:
        if item.offered_by_id == user_id and item.card_id == card_id:
            if item.qty > 1:
                item.qty -= 1
            else:
                await session.delete(item)
            trade.ready_initiator = False
            trade.ready_counterparty = False
            await session.commit()
            return True
    return False


async def cancel_trade(session: AsyncSession, trade: Trade) -> None:
    trade.status = "cancelled"
    await session.commit()


async def execute_trade(session: AsyncSession, trade: Trade) -> None:
    for item in list(trade.items):
        receiver_id = (
            trade.counterparty_id if item.offered_by_id == trade.initiator_id else trade.initiator_id
        )
        giver_uc = await session.get(UserCard, (item.offered_by_id, item.card_id))
        if giver_uc:
            giver_uc.count -= item.qty
            if giver_uc.count <= 0:
                await session.delete(giver_uc)

        receiver_uc = await session.get(UserCard, (receiver_id, item.card_id))
        if receiver_uc is None:
            receiver_uc = UserCard(user_id=receiver_id, card_id=item.card_id, count=0)
            session.add(receiver_uc)
            await session.flush()
        receiver_uc.count += item.qty
        receiver_uc.last_obtained_at = utcnow()

    trade.status = "completed"
    await session.commit()


async def find_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(func.lower(User.username) == username.lower()))
    return result.scalar_one_or_none()

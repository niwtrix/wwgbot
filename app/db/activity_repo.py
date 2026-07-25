from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActivityLog

EVENT_TYPES = ["pull", "extra_roll", "case_open", "trade", "token_grant", "broadcast", "referral", "daily_bonus"]

EVENT_LABELS = {
    "pull": "🎴 Пуллы",
    "extra_roll": "💰 Доп. роллы",
    "case_open": "🎁 Кейсы",
    "trade": "🔁 Трейды",
    "token_grant": "🪙 Начисления",
    "broadcast": "📢 Рассылки",
    "referral": "🔗 Рефералы",
    "daily_bonus": "📅 Ежедневный бонус",
}


def log_event(session: AsyncSession, event_type: str, user_id: int | None, detail: str) -> None:
    """Queue an activity-log row on the current session. Does NOT commit — the caller's
    own commit (which persists the actual state change) will save this alongside it."""
    session.add(ActivityLog(event_type=event_type, user_id=user_id, detail=detail))


async def list_events(
    session: AsyncSession, event_type: str | None, page: int, page_size: int
) -> tuple[list[ActivityLog], int]:
    count_query = select(func.count()).select_from(ActivityLog)
    query = select(ActivityLog).order_by(ActivityLog.created_at.desc())
    if event_type:
        count_query = count_query.where(ActivityLog.event_type == event_type)
        query = query.where(ActivityLog.event_type == event_type)

    total = (await session.execute(count_query)).scalar_one()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    result = await session.execute(query.limit(page_size).offset(page * page_size))
    return list(result.scalars().all()), total_pages

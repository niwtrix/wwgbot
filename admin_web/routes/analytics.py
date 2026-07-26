import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import require_auth
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.db.models import ActivityLog, Card, Rarity, User, UserCard

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

DAYS_BACK = 14


@router.get("/analytics")
async def analytics_page(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp

    since = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    day_expr = func.strftime("%Y-%m-%d", ActivityLog.created_at)

    activity_result = await session.execute(
        select(day_expr, ActivityLog.event_type, func.count())
        .where(ActivityLog.created_at >= since)
        .group_by(day_expr, ActivityLog.event_type)
    )
    days = [(since + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(DAYS_BACK + 1)]
    by_day_type: dict[str, dict[str, int]] = {d: {} for d in days}
    for day, etype, count in activity_result.all():
        by_day_type.setdefault(day, {})[etype] = count

    pulls_series = [
        by_day_type.get(d, {}).get("pull", 0) + by_day_type.get(d, {}).get("extra_roll", 0) + by_day_type.get(d, {}).get("case_open", 0)
        for d in days
    ]

    join_day_expr = func.strftime("%Y-%m-%d", User.joined_at)
    joins_result = await session.execute(
        select(join_day_expr, func.count()).where(User.joined_at >= since).group_by(join_day_expr)
    )
    joins_by_day = dict(joins_result.all())
    joins_series = [joins_by_day.get(d, 0) for d in days]

    rarity_result = await session.execute(
        select(Rarity.name, Rarity.emoji_fallback, func.coalesce(func.sum(UserCard.count), 0))
        .select_from(Rarity)
        .outerjoin(Card, Card.rarity_id == Rarity.id)
        .outerjoin(UserCard, UserCard.card_id == Card.id)
        .group_by(Rarity.id)
        .order_by(Rarity.sort_order)
    )
    rarity_rows = rarity_result.all()

    top_result = await session.execute(select(User.full_name, User.username, User.tokens).order_by(User.tokens.desc()).limit(10))
    top_rows = top_result.all()

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "active": "analytics",
            "days_json": json.dumps([d[5:] for d in days]),
            "pulls_json": json.dumps(pulls_series),
            "joins_json": json.dumps(joins_series),
            "rarity_labels_json": json.dumps([f"{emoji} {name}" for name, emoji, _ in rarity_rows]),
            "rarity_values_json": json.dumps([int(v) for _, _, v in rarity_rows]),
            "top_labels_json": json.dumps([full_name or (f"@{username}" if username else "?") for full_name, username, _ in top_rows]),
            "top_values_json": json.dumps([tokens for *_, tokens in top_rows]),
        },
    )

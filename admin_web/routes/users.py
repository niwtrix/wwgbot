from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from admin_web.auth import current_user, require_perm
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.db.activity_repo import log_event
from app.db.models import ActivityLog, Card, User, UserCard

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

PAGE_SIZE = 25


@router.get("/users")
async def users_list(request: Request, q: str = "", page: int = 0, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, "can_users")) is not None:
        return resp

    query = select(User).order_by(User.tokens.desc())
    count_query = select(func.count()).select_from(User)
    if q.strip():
        like = f"%{q.strip()}%"
        cond = or_(User.username.ilike(like), User.full_name.ilike(like), User.id == (int(q) if q.isdigit() else -1))
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = (await session.execute(count_query)).scalar_one()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    result = await session.execute(query.limit(PAGE_SIZE).offset(page * PAGE_SIZE))
    users = list(result.scalars().all())

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "user": current_user(request),
            "active": "users",
            "users": users,
            "q": q,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.get("/users/{user_id}")
async def user_detail(user_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, "can_users")) is not None:
        return resp

    user = await session.get(User, user_id)
    if user is None:
        return RedirectResponse(url="/users", status_code=303)

    rank_tokens = (
        await session.execute(select(func.count()).select_from(User).where(User.tokens > user.tokens))
    ).scalar_one() + 1

    total_pulls = (
        await session.execute(select(func.coalesce(func.sum(UserCard.count), 0)).where(UserCard.user_id == user.id))
    ).scalar_one()

    pulls_subq = select(UserCard.user_id, func.sum(UserCard.count).label("total")).group_by(UserCard.user_id).subquery()
    rank_cards = (
        await session.execute(select(func.count()).select_from(pulls_subq).where(pulls_subq.c.total > total_pulls))
    ).scalar_one() + 1

    owned_result = await session.execute(
        select(UserCard)
        .where(UserCard.user_id == user_id)
        .options(selectinload(UserCard.card).selectinload(Card.rarity))
        .join(Card)
        .order_by(Card.name)
    )
    owned_cards = list(owned_result.scalars().all())

    referred_by = await session.get(User, user.referred_by_id) if user.referred_by_id else None
    referral_count = (
        await session.execute(select(func.count()).select_from(User).where(User.referred_by_id == user_id))
    ).scalar_one()

    log_result = await session.execute(
        select(ActivityLog).where(ActivityLog.user_id == user_id).order_by(ActivityLog.created_at.desc()).limit(20)
    )
    recent_events = list(log_result.scalars().all())

    return templates.TemplateResponse(
        "user_detail.html",
        {
            "request": request,
            "user": current_user(request),
            "active": "users",
            "profile": user,
            "rank_tokens": rank_tokens,
            "rank_cards": rank_cards,
            "total_pulls": total_pulls,
            "owned_cards": owned_cards,
            "referred_by": referred_by,
            "referral_count": referral_count,
            "recent_events": recent_events,
        },
    )


@router.post("/users/{user_id}/grant")
async def grant_tokens(user_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, "can_users")) is not None:
        return resp
    form = await request.form()
    try:
        amount = int(form.get("amount", "0"))
    except ValueError:
        amount = 0

    user = await session.get(User, user_id)
    if user is not None and amount != 0:
        user.tokens = max(0, user.tokens + amount)
        sign = "+" if amount >= 0 else ""
        label = f"@{user.username}" if user.username else (user.full_name or str(user.id))
        log_event(session, "token_grant", user_id, f"Веб-админ начислил(а) {label}: {sign}{amount} 🪙 (стало {user.tokens})")
        await session.commit()

    next_url = str(form.get("next", "") or "/users")
    return RedirectResponse(url=next_url, status_code=303)

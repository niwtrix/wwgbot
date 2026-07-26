from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import require_auth
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.db.activity_repo import log_event
from app.db.models import User

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

PAGE_SIZE = 25


@router.get("/users")
async def users_list(request: Request, q: str = "", page: int = 0, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
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
            "active": "users",
            "users": users,
            "q": q,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.post("/users/{user_id}/grant")
async def grant_tokens(user_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
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

    return RedirectResponse(url="/users", status_code=303)

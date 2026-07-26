from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import require_auth
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from admin_web.monitor import recent_logs, service_status, system_stats
from app.db.models import Card, Trade, User, UserCard

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

BOT_SERVICE = "wwgang-bot.service"


@router.get("/")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp

    users_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    cards_count = (await session.execute(select(func.count()).select_from(Card))).scalar_one()
    total_tokens = (await session.execute(select(func.coalesce(func.sum(User.tokens), 0)))).scalar_one()
    total_pulls = (await session.execute(select(func.coalesce(func.sum(UserCard.count), 0)))).scalar_one()
    active_trades = (
        await session.execute(select(func.count()).select_from(Trade).where(Trade.status.in_(("pending", "active", "confirming"))))
    ).scalar_one()

    stats = system_stats()
    bot_status = service_status(BOT_SERVICE)
    logs = recent_logs(BOT_SERVICE, 40)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active": "dashboard",
            "users_count": users_count,
            "cards_count": cards_count,
            "total_tokens": total_tokens,
            "total_pulls": total_pulls,
            "active_trades": active_trades,
            "stats": stats,
            "bot_status": bot_status,
            "logs": logs,
        },
    )

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import current_user, require_perm
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.db.activity_repo import EVENT_LABELS, EVENT_TYPES, list_events

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

PAGE_SIZE = 30


@router.get("/log")
async def log_page(
    request: Request, type: str = "all", page: int = 0, session: AsyncSession = Depends(get_session)
):
    if (resp := require_perm(request, "can_log")) is not None:
        return resp
    event_type = None if type == "all" else type
    events, total_pages = await list_events(session, event_type, page, PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    return templates.TemplateResponse(
        "log.html",
        {
            "request": request,
            "user": current_user(request),
            "active": "log",
            "events": events,
            "event_types": EVENT_TYPES,
            "event_labels": EVENT_LABELS,
            "current_type": type,
            "page": page,
            "total_pages": total_pages,
        },
    )

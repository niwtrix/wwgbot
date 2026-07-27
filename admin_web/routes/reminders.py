from aiogram import Bot
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import current_user, require_perm
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.config import BOT_TOKEN
from app.db.settings_repo import all_settings, set_setting
from app.services.bonus_reminders import send_preview

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

PERM = "can_settings"

FIELDS = [
    "reminder_a_enabled",
    "reminder_a_hour_utc",
    "reminder_a_emoji_id",
    "reminder_a_text",
    "reminder_b_enabled",
    "reminder_b_window_start_hour_utc",
    "reminder_b_window_end_hour_utc",
    "reminder_b_min_streak",
    "reminder_b_emoji_id",
    "reminder_b_text",
]


@router.get("/reminders")
async def reminders_page(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    values = await all_settings(session)
    return templates.TemplateResponse(
        "reminders.html",
        {"request": request, "user": current_user(request), "active": "reminders", "values": values, "result": None},
    )


@router.post("/reminders")
async def reminders_submit(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    form = await request.form()

    for key in FIELDS:
        if key.endswith("_enabled"):
            await set_setting(session, key, "1" if form.get(key) == "on" else "0")
        elif key in form:
            await set_setting(session, key, str(form.get(key, "")))

    return RedirectResponse(url="/reminders", status_code=303)


@router.post("/reminders/preview")
async def reminders_preview(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    form = await request.form()
    kind = str(form.get("kind", "a"))
    username = str(form.get("username", "")).strip()

    result = None
    if username:
        bot = Bot(token=BOT_TOKEN)
        try:
            result = await send_preview(bot, session, kind, username)
        finally:
            await bot.session.close()

    values = await all_settings(session)
    return templates.TemplateResponse(
        "reminders.html",
        {"request": request, "user": current_user(request), "active": "reminders", "values": values, "result": result},
    )

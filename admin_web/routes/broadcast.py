import asyncio

from aiogram import Bot
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import current_user, require_perm
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.config import BOT_TOKEN
from app.db.activity_repo import log_event
from app.db.models import User

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/broadcast")
async def broadcast_form(request: Request):
    if (resp := require_perm(request, "can_broadcast")) is not None:
        return resp
    return templates.TemplateResponse(
        "broadcast.html", {"request": request,
            "user": current_user(request), "active": "broadcast", "result": None}
    )


@router.post("/broadcast")
async def broadcast_submit(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, "can_broadcast")) is not None:
        return resp
    form = await request.form()
    text = str(form.get("text", "")).strip()
    use_html = form.get("html") == "on"

    if not text:
        return templates.TemplateResponse(
            "broadcast.html", {"request": request,
            "user": current_user(request), "active": "broadcast", "result": "Пустое сообщение — не отправлено."}
        )

    result = await session.execute(select(User.id))
    user_ids = [row[0] for row in result.all()]

    bot = Bot(token=BOT_TOKEN)
    sent = failed = 0
    try:
        for user_id in user_ids:
            try:
                await bot.send_message(user_id, text, parse_mode="HTML" if use_html else None)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
    finally:
        await bot.session.close()

    log_event(session, "broadcast", None, f"Веб-админ: доставлено {sent}, не удалось {failed}")
    await session.commit()

    return templates.TemplateResponse(
        "broadcast.html",
        {"request": request,
            "user": current_user(request), "active": "broadcast", "result": f"Доставлено: {sent}, не удалось: {failed}"},
    )

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import require_auth
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.db.cards_repo import list_rarities
from app.db.models import Card, Rarity

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/rarities")
async def rarities_list(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    rarities = await list_rarities(session)
    counts = {}
    for r in rarities:
        counts[r.id] = (
            await session.execute(select(func.count()).select_from(Card).where(Card.rarity_id == r.id))
        ).scalar_one()
    return templates.TemplateResponse(
        "rarities.html", {"request": request, "active": "rarities", "rarities": rarities, "counts": counts}
    )


@router.get("/rarities/new")
async def rarity_new_form(request: Request):
    if (resp := require_auth(request)) is not None:
        return resp
    return templates.TemplateResponse("rarity_edit.html", {"request": request, "active": "rarities", "rarity": None})


@router.post("/rarities/new")
async def rarity_new_submit(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    form = await request.form()
    name = str(form.get("name", "")).strip()

    base = re.sub(r"[^a-z0-9_]+", "", name.lower()) or "rarity"
    slug = base
    n = 1
    while await session.get(Rarity, slug):
        n += 1
        slug = f"{base}{n}"

    max_order = (await session.execute(select(func.max(Rarity.sort_order)))).scalar_one() or 0

    rarity = Rarity(
        id=slug,
        name=name,
        weight=float(form.get("weight") or 10),
        token_reward=int(form.get("token_reward") or 5),
        emoji_fallback=str(form.get("emoji_fallback") or "🔹"),
        emoji_id=str(form.get("emoji_id", "")).strip() or None,
        sort_order=max_order + 1,
        case_only=form.get("case_only") == "on",
    )
    session.add(rarity)
    await session.commit()
    return RedirectResponse(url="/rarities", status_code=303)


@router.get("/rarities/{rarity_id}/edit")
async def rarity_edit_form(rarity_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    rarity = await session.get(Rarity, rarity_id)
    if rarity is None:
        return RedirectResponse(url="/rarities", status_code=303)
    return templates.TemplateResponse("rarity_edit.html", {"request": request, "active": "rarities", "rarity": rarity})


@router.post("/rarities/{rarity_id}/edit")
async def rarity_edit_submit(rarity_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    rarity = await session.get(Rarity, rarity_id)
    if rarity is None:
        return RedirectResponse(url="/rarities", status_code=303)

    form = await request.form()
    rarity.name = str(form.get("name", "")).strip()
    rarity.weight = float(form.get("weight") or rarity.weight)
    rarity.token_reward = int(form.get("token_reward") or rarity.token_reward)
    rarity.emoji_fallback = str(form.get("emoji_fallback") or rarity.emoji_fallback)
    rarity.emoji_id = str(form.get("emoji_id", "")).strip() or None
    rarity.case_only = form.get("case_only") == "on"
    await session.commit()
    return RedirectResponse(url="/rarities", status_code=303)


@router.post("/rarities/{rarity_id}/delete")
async def rarity_delete(rarity_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    count = (
        await session.execute(select(func.count()).select_from(Card).where(Card.rarity_id == rarity_id))
    ).scalar_one()
    if count == 0:
        rarity = await session.get(Rarity, rarity_id)
        if rarity is not None:
            await session.delete(rarity)
            await session.commit()
    return RedirectResponse(url="/rarities", status_code=303)

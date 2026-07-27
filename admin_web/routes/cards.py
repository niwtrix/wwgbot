import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import current_user, require_perm
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.config import CARDS_DIR
from app.db.cards_repo import list_all_cards, list_rarities
from app.db.models import Card

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

PERM = "can_cards"


def _unique_slug_sync(existing_slugs: set[str], name: str) -> str:
    base = re.sub(r"[^a-z0-9_]+", "", name.lower()) or "card"
    slug = base
    n = 1
    while slug in existing_slugs:
        n += 1
        slug = f"{base}{n}"
    return slug


def _is_upload(value) -> bool:
    """True for an actual chosen file. request.form() returns starlette's UploadFile for
    file inputs (not fastapi's — that's a *subclass*, so isinstance(x, fastapi.UploadFile)
    is false for it), so check duck-typed instead of by class."""
    return bool(value) and hasattr(value, "filename") and hasattr(value, "read") and bool(getattr(value, "filename", ""))


@router.get("/cards")
async def cards_list(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    cards = await list_all_cards(session)
    return templates.TemplateResponse(
        "cards.html", {"request": request, "user": current_user(request), "active": "cards", "cards": cards}
    )


@router.get("/cards/new")
async def card_new_form(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    rarities = await list_rarities(session)
    return templates.TemplateResponse(
        "card_edit.html",
        {"request": request, "user": current_user(request), "active": "cards", "card": None, "rarities": rarities},
    )


@router.post("/cards/new")
async def card_new_submit(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    form = await request.form()

    result = await session.execute(select(Card.slug))
    existing_slugs = {row[0] for row in result.all()}
    slug = _unique_slug_sync(existing_slugs, str(form.get("name", "card")))

    card = Card(
        slug=slug,
        name=str(form.get("name", "")).strip(),
        role=str(form.get("role", "")).strip(),
        quote=str(form.get("quote", "")).strip(),
        telegram_url=str(form.get("telegram_url", "")).strip() or None,
        youtube_url=str(form.get("youtube_url", "")).strip() or None,
        twitch_url=str(form.get("twitch_url", "")).strip() or None,
        rarity_id=str(form.get("rarity_id", "")),
        is_active=form.get("is_active") == "on",
    )
    session.add(card)
    await session.flush()

    photo = form.get("photo")
    if _is_upload(photo):
        await _save_photo(card, photo)

    await session.commit()
    return RedirectResponse(url="/cards", status_code=303)


@router.get("/cards/{card_id}/edit")
async def card_edit_form(card_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    card = await session.get(Card, card_id)
    if card is None:
        return RedirectResponse(url="/cards", status_code=303)
    rarities = await list_rarities(session)
    return templates.TemplateResponse(
        "card_edit.html",
        {"request": request, "user": current_user(request), "active": "cards", "card": card, "rarities": rarities},
    )


async def _save_photo(card: Card, photo) -> None:
    filename_in = photo.filename or ""
    ext = (filename_in.rsplit(".", 1)[-1] if "." in filename_in else "png").lower()
    if ext not in ("png", "jpg", "jpeg", "webp"):
        ext = "png"
    filename = f"{card.slug}.{ext}"
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    content = await photo.read()
    (CARDS_DIR / filename).write_bytes(content)
    card.photo_file = filename
    card.tg_file_id = None  # photo changed — force re-upload to Telegram on next send


@router.post("/cards/{card_id}/edit")
async def card_edit_submit(card_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    card = await session.get(Card, card_id)
    if card is None:
        return RedirectResponse(url="/cards", status_code=303)

    form = await request.form()
    card.name = str(form.get("name", "")).strip()
    card.role = str(form.get("role", "")).strip()
    card.quote = str(form.get("quote", "")).strip()
    card.telegram_url = str(form.get("telegram_url", "")).strip() or None
    card.youtube_url = str(form.get("youtube_url", "")).strip() or None
    card.twitch_url = str(form.get("twitch_url", "")).strip() or None
    card.rarity_id = str(form.get("rarity_id", card.rarity_id))
    card.is_active = form.get("is_active") == "on"

    photo = form.get("photo")
    if _is_upload(photo):
        await _save_photo(card, photo)

    await session.commit()
    return RedirectResponse(url="/cards", status_code=303)


@router.post("/cards/{card_id}/delete")
async def card_delete(card_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    card = await session.get(Card, card_id)
    if card is not None:
        await session.delete(card)
        await session.commit()
    return RedirectResponse(url="/cards", status_code=303)


@router.post("/cards/{card_id}/toggle")
async def card_toggle(card_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_perm(request, PERM)) is not None:
        return resp
    card = await session.get(Card, card_id)
    if card is not None:
        card.is_active = not card.is_active
        await session.commit()
    return RedirectResponse(url="/cards", status_code=303)

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
from app.db.cases_repo import get_case, list_cases, set_case_odds
from app.db.models import Case

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/cases")
async def cases_list(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    cases = await list_cases(session)
    return templates.TemplateResponse("cases.html", {"request": request, "active": "cases", "cases": cases})


@router.get("/cases/new")
async def case_new_form(request: Request):
    if (resp := require_auth(request)) is not None:
        return resp
    return templates.TemplateResponse(
        "case_edit.html", {"request": request, "active": "cases", "case": None, "rarities": []}
    )


@router.post("/cases/new")
async def case_new_submit(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    form = await request.form()
    name = str(form.get("name", "")).strip()

    result = await session.execute(select(Case.slug))
    existing = {row[0] for row in result.all()}
    base = re.sub(r"[^a-z0-9_]+", "", name.lower()) or "case"
    slug = base
    n = 1
    while slug in existing:
        n += 1
        slug = f"{base}{n}"

    max_order = (await session.execute(select(func.max(Case.sort_order)))).scalar_one() or 0

    case = Case(
        slug=slug,
        name=name,
        price_tokens=int(form.get("price_tokens") or 100),
        description=str(form.get("description", "")).strip(),
        is_active=form.get("is_active") == "on",
        sort_order=max_order + 1,
    )
    session.add(case)
    await session.commit()
    return RedirectResponse(url=f"/cases/{case.id}/edit", status_code=303)


@router.get("/cases/{case_id}/edit")
async def case_edit_form(case_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    case = await get_case(session, case_id)
    if case is None:
        return RedirectResponse(url="/cases", status_code=303)
    rarities = await list_rarities(session)
    odds_by_rarity = {o.rarity_id: o.weight for o in case.odds}
    return templates.TemplateResponse(
        "case_edit.html",
        {"request": request, "active": "cases", "case": case, "rarities": rarities, "odds_by_rarity": odds_by_rarity},
    )


@router.post("/cases/{case_id}/edit")
async def case_edit_submit(case_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    case = await session.get(Case, case_id)
    if case is None:
        return RedirectResponse(url="/cases", status_code=303)

    form = await request.form()
    case.name = str(form.get("name", "")).strip()
    case.price_tokens = int(form.get("price_tokens") or case.price_tokens)
    case.description = str(form.get("description", "")).strip()
    case.is_active = form.get("is_active") == "on"
    await session.commit()

    rarities = await list_rarities(session)
    for r in rarities:
        raw = str(form.get(f"weight_{r.id}", "")).strip().replace(",", ".")
        weight = float(raw) if raw else 0.0
        await set_case_odds(session, case_id, r.id, weight)

    return RedirectResponse(url=f"/cases/{case_id}/edit", status_code=303)


@router.post("/cases/{case_id}/delete")
async def case_delete(case_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    case = await session.get(Case, case_id)
    if case is not None:
        await session.delete(case)
        await session.commit()
    return RedirectResponse(url="/cases", status_code=303)

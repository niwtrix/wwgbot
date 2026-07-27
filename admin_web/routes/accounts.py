from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import PERM_KEYS, PERM_LABELS, current_user, hash_password
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.db.models import AdminAccount

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _require_owner(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not user.get("is_owner"):
        return RedirectResponse(url="/?denied=1", status_code=303)
    return None


@router.get("/accounts")
async def accounts_list(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := _require_owner(request)) is not None:
        return resp
    result = await session.execute(select(AdminAccount).order_by(AdminAccount.id))
    accounts = list(result.scalars().all())
    return templates.TemplateResponse(
        "accounts.html",
        {"request": request, "active": "accounts", "accounts": accounts, "perm_keys": PERM_KEYS, "perm_labels": PERM_LABELS},
    )


@router.get("/accounts/new")
async def account_new_form(request: Request):
    if (resp := _require_owner(request)) is not None:
        return resp
    return templates.TemplateResponse(
        "account_edit.html",
        {"request": request, "active": "accounts", "account": None, "perm_keys": PERM_KEYS, "perm_labels": PERM_LABELS},
    )


@router.post("/accounts/new")
async def account_new_submit(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := _require_owner(request)) is not None:
        return resp
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    if not username or len(password) < 6:
        accounts_result = await session.execute(select(AdminAccount).order_by(AdminAccount.id))
        return templates.TemplateResponse(
            "account_edit.html",
            {
                "request": request, "active": "accounts", "account": None,
                "perm_keys": PERM_KEYS, "perm_labels": PERM_LABELS,
                "error": "Логин обязателен, пароль — минимум 6 символов.",
            },
        )

    existing = (await session.execute(select(AdminAccount).where(AdminAccount.username == username))).scalar_one_or_none()
    if existing is not None:
        return templates.TemplateResponse(
            "account_edit.html",
            {
                "request": request, "active": "accounts", "account": None,
                "perm_keys": PERM_KEYS, "perm_labels": PERM_LABELS,
                "error": f"Логин «{username}» уже занят.",
            },
        )

    digest, salt = hash_password(password)
    account = AdminAccount(
        username=username,
        password_hash=digest,
        password_salt=salt,
        is_owner=False,
        **{key: form.get(key) == "on" for key in PERM_KEYS},
    )
    session.add(account)
    await session.commit()
    return RedirectResponse(url="/accounts", status_code=303)


@router.get("/accounts/{account_id}/edit")
async def account_edit_form(account_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := _require_owner(request)) is not None:
        return resp
    account = await session.get(AdminAccount, account_id)
    if account is None:
        return RedirectResponse(url="/accounts", status_code=303)
    return templates.TemplateResponse(
        "account_edit.html",
        {"request": request, "active": "accounts", "account": account, "perm_keys": PERM_KEYS, "perm_labels": PERM_LABELS},
    )


@router.post("/accounts/{account_id}/edit")
async def account_edit_submit(account_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := _require_owner(request)) is not None:
        return resp
    account = await session.get(AdminAccount, account_id)
    if account is None:
        return RedirectResponse(url="/accounts", status_code=303)

    form = await request.form()
    new_password = str(form.get("password", "")).strip()
    if new_password:
        if len(new_password) < 6:
            return templates.TemplateResponse(
                "account_edit.html",
                {
                    "request": request, "active": "accounts", "account": account,
                    "perm_keys": PERM_KEYS, "perm_labels": PERM_LABELS,
                    "error": "Пароль — минимум 6 символов.",
                },
            )
        account.password_hash, account.password_salt = hash_password(new_password)

    if not account.is_owner:
        for key in PERM_KEYS:
            setattr(account, key, form.get(key) == "on")

    await session.commit()
    return RedirectResponse(url="/accounts", status_code=303)


@router.post("/accounts/{account_id}/delete")
async def account_delete(account_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := _require_owner(request)) is not None:
        return resp
    user = current_user(request)
    account = await session.get(AdminAccount, account_id)
    if account is not None and account.id != user["id"] and not account.is_owner:
        await session.delete(account)
        await session.commit()
    return RedirectResponse(url="/accounts", status_code=303)

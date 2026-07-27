import hashlib
import hmac
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.db.models import AdminAccount

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

PERM_KEYS = [
    "can_cards",
    "can_rarities",
    "can_cases",
    "can_settings",
    "can_users",
    "can_log",
    "can_analytics",
    "can_broadcast",
]

PERM_LABELS = {
    "can_cards": "Карточки",
    "can_rarities": "Редкости",
    "can_cases": "Кейсы",
    "can_settings": "Настройки",
    "can_users": "Пользователи (начисление токенов)",
    "can_log": "Лог событий",
    "can_analytics": "Аналитика",
    "can_broadcast": "Рассылка",
}


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return digest, salt


def verify_password(password: str, digest: str, salt: str) -> bool:
    check, _ = hash_password(password, salt)
    return hmac.compare_digest(check, digest)


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


def require_auth(request: Request):
    if current_user(request) is None:
        return RedirectResponse(url="/login", status_code=303)
    return None


def require_perm(request: Request, perm: str | None = None):
    """Return a redirect response if access should be blocked, else None (proceed)."""
    user = current_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if perm and not user.get("is_owner") and not user.get("perms", {}).get(perm):
        return RedirectResponse(url="/?denied=1", status_code=303)
    return None


def _session_payload(account: AdminAccount) -> dict:
    return {
        "id": account.id,
        "username": account.username,
        "is_owner": account.is_owner,
        "perms": {key: getattr(account, key) for key in PERM_KEYS},
    }


@router.get("/setup")
async def setup_form(request: Request, session: AsyncSession = Depends(get_session)):
    count = (await session.execute(select(func.count()).select_from(AdminAccount))).scalar_one()
    if count > 0:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("setup.html", {"request": request, "error": None})


@router.post("/setup")
async def setup_submit(request: Request, session: AsyncSession = Depends(get_session)):
    count = (await session.execute(select(func.count()).select_from(AdminAccount))).scalar_one()
    if count > 0:
        return RedirectResponse(url="/login", status_code=303)

    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    if not username or len(password) < 6:
        return templates.TemplateResponse(
            "setup.html", {"request": request, "error": "Имя пользователя обязательно, пароль — минимум 6 символов."}
        )

    digest, salt = hash_password(password)
    account = AdminAccount(
        username=username,
        password_hash=digest,
        password_salt=salt,
        is_owner=True,
        **{key: True for key in PERM_KEYS},
    )
    session.add(account)
    await session.commit()

    request.session["user"] = _session_payload(account)
    return RedirectResponse(url="/", status_code=303)


@router.get("/login")
async def login_form(request: Request, session: AsyncSession = Depends(get_session)):
    if current_user(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    count = (await session.execute(select(func.count()).select_from(AdminAccount))).scalar_one()
    if count == 0:
        return RedirectResponse(url="/setup", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    result = await session.execute(select(AdminAccount).where(AdminAccount.username == username))
    account = result.scalar_one_or_none()

    if account is not None and verify_password(password, account.password_hash, account.password_salt):
        request.session["user"] = _session_payload(account)
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Неверный логин или пароль"}, status_code=401
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

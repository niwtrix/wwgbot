import hmac

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from admin_web.config import ADMIN_PANEL_PASSWORD, TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def is_authed(request: Request) -> bool:
    return bool(request.session.get("authed"))


def require_auth(request: Request) -> RedirectResponse | None:
    """Call at the top of a protected route; if it returns a response, return that
    response immediately instead of continuing."""
    if not is_authed(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


@router.get("/login")
async def login_form(request: Request):
    if is_authed(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    password = str(form.get("password", ""))
    if hmac.compare_digest(password, ADMIN_PANEL_PASSWORD):
        request.session["authed"] = True
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Неверный пароль"}, status_code=401
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

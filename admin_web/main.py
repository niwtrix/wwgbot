from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from admin_web import auth
from admin_web.config import ADMIN_SESSION_SECRET, STATIC_DIR
from admin_web.routes import accounts, analytics, broadcast, cards, cases, dashboard, log, rarities, reminders, settings, users
from app.config import CARDS_DIR

app = FastAPI(title="WWGang Admin")
app.add_middleware(SessionMiddleware, secret_key=ADMIN_SESSION_SECRET, session_cookie="wwgadmin_session")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
CARDS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/card-images", StaticFiles(directory=str(CARDS_DIR)), name="card-images")

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(dashboard.router)
app.include_router(cards.router)
app.include_router(rarities.router)
app.include_router(cases.router)
app.include_router(settings.router)
app.include_router(reminders.router)
app.include_router(users.router)
app.include_router(log.router)
app.include_router(analytics.router)
app.include_router(broadcast.router)

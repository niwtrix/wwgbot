from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from admin_web.auth import require_auth
from admin_web.config import TEMPLATES_DIR
from admin_web.deps import get_session
from app.db.settings_repo import all_settings, set_setting

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

TEXT_KEYS = {"start_text", "help_text"}

FIELD_GROUPS = [
    ("Экономика", ["cooldown_minutes", "duplicate_bonus", "extra_roll_price"]),
    ("Защита от дублей", ["pity_floor_pulls", "pity_ramp_pulls", "pity_min_weight_fraction"]),
    ("Реферальная программа", ["referral_bonus_tokens"]),
    ("Ежедневный бонус", ["daily_bonus_base_tokens", "daily_bonus_streak_step", "daily_bonus_max_tokens"]),
    ("Автоотчёты о статусе", ["health_report_enabled", "health_report_interval_minutes"]),
    ("Тексты команд", ["start_text", "help_text"]),
]

LABELS = {
    "cooldown_minutes": "Кулдаун между попытками (минуты)",
    "duplicate_bonus": "Бонус токенов за дубликат",
    "extra_roll_price": "Цена доп. ролла (токены)",
    "pity_floor_pulls": "Мин. пуллов до повтора карты",
    "pity_ramp_pulls": "Пуллов на восстановление шанса",
    "pity_min_weight_fraction": "Мин. доля шанса (0–1)",
    "referral_bonus_tokens": "Бонус за реферала (токены)",
    "daily_bonus_base_tokens": "Ежедневный бонус: база (токены)",
    "daily_bonus_streak_step": "Ежедневный бонус: прирост за день серии",
    "daily_bonus_max_tokens": "Ежедневный бонус: максимум",
    "health_report_enabled": "Автоотчёты включены (1/0)",
    "health_report_interval_minutes": "Интервал автоотчётов (минуты)",
    "start_text": "Текст команды /start",
    "help_text": "Текст команды /help",
}


@router.get("/settings")
async def settings_page(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    values = await all_settings(session)
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active": "settings",
            "values": values,
            "groups": FIELD_GROUPS,
            "labels": LABELS,
            "text_keys": TEXT_KEYS,
        },
    )


@router.post("/settings")
async def settings_submit(request: Request, session: AsyncSession = Depends(get_session)):
    if (resp := require_auth(request)) is not None:
        return resp
    form = await request.form()
    for _, keys in FIELD_GROUPS:
        for key in keys:
            if key in form:
                await set_setting(session, key, str(form.get(key, "")))
    return RedirectResponse(url="/settings", status_code=303)

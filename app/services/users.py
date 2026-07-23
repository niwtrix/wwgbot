from datetime import datetime, timezone

from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def get_or_create_user(session: AsyncSession, tg_user: TgUser) -> User:
    user = await session.get(User, tg_user.id)
    if user is None:
        user = User(
            id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        session.add(user)
        await session.commit()
        return user

    changed = False
    if user.username != tg_user.username:
        user.username = tg_user.username
        changed = True
    if user.full_name != tg_user.full_name:
        user.full_name = tg_user.full_name
        changed = True
    if changed:
        await session.commit()
    return user


def seconds_until_ready(user: User, cooldown_minutes: int) -> int:
    if user.last_pull_at is None:
        return 0
    last = user.last_pull_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    remaining = cooldown_minutes * 60 - elapsed
    return max(0, int(remaining))

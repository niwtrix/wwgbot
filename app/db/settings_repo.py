from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.defaults import DEFAULT_SETTINGS
from app.db.models import Setting

_cache: dict[str, str] = {}


async def get_setting(session: AsyncSession, key: str) -> str:
    if key in _cache:
        return _cache[key]
    row = await session.get(Setting, key)
    value = row.value if row else DEFAULT_SETTINGS.get(key, "")
    _cache[key] = value
    return value


async def get_setting_int(session: AsyncSession, key: str) -> int:
    return int(await get_setting(session, key))


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    _cache[key] = value
    await session.commit()


async def all_settings(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(Setting))
    db_values = {s.key: s.value for s in result.scalars().all()}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(db_values)
    return merged

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session

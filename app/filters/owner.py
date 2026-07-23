from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.config import OWNER_IDS


class IsOwner(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in OWNER_IDS)

"""One-off full reset: wipes cards, user collections, rarities and cases, then reseeds
fresh from the current data/cards_seed.json + app/db/defaults.py. Use when replacing the
whole card pack or restructuring rarities, not for routine incremental additions."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.engine import async_session, init_db  # noqa: E402
from app.db.models import Card, Case, CaseCardOdds, CaseOdds, Rarity, UserCard  # noqa: E402
from scripts.seed import seed_cards, seed_cases, seed_rarities, seed_settings  # noqa: E402


async def wipe() -> None:
    async with async_session() as session:
        await session.execute(UserCard.__table__.delete())
        await session.execute(CaseCardOdds.__table__.delete())
        await session.execute(CaseOdds.__table__.delete())
        await session.execute(Case.__table__.delete())
        await session.execute(Card.__table__.delete())
        await session.execute(Rarity.__table__.delete())
        await session.commit()
    print("Wiped: user_cards, case_card_odds, case_odds, cases, cards, rarities")


async def main() -> None:
    await init_db()
    await wipe()
    await seed_rarities()
    await seed_settings()
    await seed_cards()
    await seed_cases()
    print("Reset + reseed complete.")


if __name__ == "__main__":
    asyncio.run(main())

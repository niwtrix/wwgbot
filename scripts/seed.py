import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import BASE_DIR  # noqa: E402
from app.db.defaults import DEFAULT_CASES, DEFAULT_RARITIES, DEFAULT_SETTINGS  # noqa: E402
from app.db.engine import async_session, init_db  # noqa: E402
from app.db.models import Card, Case, CaseCardOdds, Rarity, Setting  # noqa: E402

CARDS_SEED_PATH = BASE_DIR / "data" / "cards_seed.json"


async def seed_rarities() -> None:
    async with async_session() as session:
        for rarity_id, name, weight, token_reward, emoji_fallback, sort_order, case_only, upgrade_value in DEFAULT_RARITIES:
            existing = await session.get(Rarity, rarity_id)
            if existing:
                continue
            session.add(
                Rarity(
                    id=rarity_id,
                    name=name,
                    weight=weight,
                    token_reward=token_reward,
                    emoji_fallback=emoji_fallback,
                    sort_order=sort_order,
                    case_only=case_only,
                    upgrade_value=upgrade_value,
                )
            )
        await session.commit()


async def seed_cases() -> None:
    async with async_session() as session:
        for slug, name, price_tokens, description, sort_order, odds in DEFAULT_CASES:
            result = await session.execute(select(Case).where(Case.slug == slug))
            if result.scalar_one_or_none():
                continue
            case = Case(
                slug=slug,
                name=name,
                price_tokens=price_tokens,
                description=description,
                sort_order=sort_order,
            )
            session.add(case)
            await session.flush()
            for rarity_id, weight in odds:
                rarity_cards = (await session.execute(select(Card).where(Card.rarity_id == rarity_id))).scalars().all()
                for card in rarity_cards:
                    session.add(CaseCardOdds(case_id=case.id, card_id=card.id, weight=weight))
        await session.commit()


async def seed_settings() -> None:
    async with async_session() as session:
        for key, value in DEFAULT_SETTINGS.items():
            existing = await session.get(Setting, key)
            if existing:
                continue
            session.add(Setting(key=key, value=value))
        await session.commit()


async def seed_cards() -> None:
    if not CARDS_SEED_PATH.exists():
        print(f"No seed file at {CARDS_SEED_PATH}, skipping card seeding.")
        return

    with open(CARDS_SEED_PATH, encoding="utf-8") as f:
        cards_data = json.load(f)

    async with async_session() as session:
        result = await session.execute(select(Card.slug))
        existing_slugs = {row[0] for row in result.all()}

        added = 0
        for c in cards_data:
            if c["slug"] in existing_slugs:
                continue
            session.add(
                Card(
                    slug=c["slug"],
                    name=c["name"],
                    role=c["role"],
                    quote=c["quote"],
                    telegram_url=c["telegram"],
                    youtube_url=c["youtube"],
                    twitch_url=c["twitch"],
                    photo_file=c["photo_file"],
                    rarity_id=c["rarity"],
                )
            )
            added += 1
        await session.commit()
        print(f"Added {added} new cards (skipped {len(cards_data) - added} already present).")


async def main() -> None:
    await init_db()
    await seed_rarities()
    await seed_settings()
    await seed_cards()
    await seed_cases()
    print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(main())

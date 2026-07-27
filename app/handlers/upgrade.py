import contextlib
import random
from collections import Counter
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.activity_repo import log_event
from app.db.cards_repo import get_card, list_active_cards, list_rarities
from app.db.models import Card, UserCard
from app.db.settings_repo import get_setting, get_setting_int
from app.keyboards.upgrade import (
    upgrade_add_picker_kb,
    upgrade_remove_picker_kb,
    upgrade_room_kb,
    upgrade_target_picker_kb,
)
from app.services.format import display_name
from app.services.users import get_or_create_user
from app.states.user import UpgradeFlow

router = Router(name="upgrade")


async def _get_upgrade_settings(session: AsyncSession) -> tuple[int, float, int, int]:
    max_items = await get_setting_int(session, "upgrade_max_sacrifice_items")
    fairness = float(await get_setting(session, "upgrade_fairness_factor"))
    min_pct = await get_setting_int(session, "upgrade_min_chance_percent")
    max_pct = await get_setting_int(session, "upgrade_max_chance_percent")
    return max_items, fairness, min_pct, max_pct


def _compute_chance(sacrifice_value: float, target_value: float, fairness: float, min_pct: int, max_pct: int) -> float:
    if target_value <= 0:
        return 0.0
    raw_pct = (sacrifice_value / target_value) * fairness * 100
    pct = max(min_pct, min(max_pct, raw_pct))
    return pct / 100


async def _owned_qty(session: AsyncSession, user_id: int, card_id: int) -> int:
    uc = await session.get(UserCard, (user_id, card_id))
    return uc.count if uc else 0


async def _owned_cards_with_avail(session: AsyncSession, user_id: int, sacrifice_ids: list[int]) -> list[tuple[Card, int]]:
    result = await session.execute(
        select(UserCard)
        .where(UserCard.user_id == user_id, UserCard.count > 0)
        .options(selectinload(UserCard.card).selectinload(Card.rarity))
        .join(Card)
        .order_by(Card.name)
    )
    owned = list(result.scalars().all())
    counts = Counter(sacrifice_ids)
    out = []
    for uc in owned:
        already = counts.get(uc.card_id, 0)
        avail = uc.count - already
        if avail > 0:
            out.append((uc.card, avail))
    return out


async def _sacrifice_items(session: AsyncSession, sacrifice_ids: list[int]) -> list[tuple[Card, int]]:
    if not sacrifice_ids:
        return []
    counts = Counter(sacrifice_ids)
    result = await session.execute(
        select(Card).where(Card.id.in_(counts.keys())).options(selectinload(Card.rarity))
    )
    card_map = {c.id: c for c in result.scalars().all()}
    return [(card_map[cid], qty) for cid, qty in counts.items() if cid in card_map]


async def _room_text(session: AsyncSession, sacrifice_ids: list[int], target_id: int | None) -> str:
    max_items, fairness, min_pct, max_pct = await _get_upgrade_settings(session)

    sac_items = await _sacrifice_items(session, sacrifice_ids)
    sacrifice_value = sum(c.rarity.upgrade_value * qty for c, qty in sac_items)

    lines = ["🔧 <b>Апгрейд карточек</b>\n", f"Ставишь ({len(sacrifice_ids)}/{max_items}):"]
    if sac_items:
        for c, qty in sac_items:
            lines.append(f"{c.rarity.emoji_fallback} {escape(c.name)} ×{qty} (цена {c.rarity.upgrade_value:g})")
    else:
        lines.append("— пока ничего —")
    lines.append(f"\nОбщая ценность ставки: {sacrifice_value:g}")
    lines.append("")

    if target_id is not None:
        target_card = await get_card(session, target_id)
        if target_card is not None:
            target_value = target_card.rarity.upgrade_value
            lines.append(f"Цель: {target_card.rarity.emoji_fallback} {escape(target_card.name)} (цена {target_value:g})")
            chance = _compute_chance(sacrifice_value, target_value, fairness, min_pct, max_pct)
            lines.append(f"\n🎲 Шанс успеха: {chance * 100:.1f}%")
        else:
            lines.append("Цель: — недоступна, выбери другую —")
    else:
        lines.append("Цель: — не выбрана —")

    return "\n".join(lines)


def _room_kb(sacrifice_ids: list[int], target_id: int | None, max_items: int):
    can_add = len(sacrifice_ids) < max_items
    can_remove = len(sacrifice_ids) > 0
    can_spin = len(sacrifice_ids) > 0 and target_id is not None
    return upgrade_room_kb(can_add, can_remove, can_spin)


@router.message(Command("upgrade"))
async def cmd_upgrade(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = await get_or_create_user(session, message.from_user)
    owned = await _owned_cards_with_avail(session, user.id, [])
    if not owned:
        await message.answer("У тебя пока нет карточек для апгрейда. Испытай удачу: /card")
        return

    await state.set_state(UpgradeFlow.active)
    await state.update_data(sacrifice=[], target_id=None)

    max_items, *_ = await _get_upgrade_settings(session)
    text = await _room_text(session, [], None)
    await message.answer(text, parse_mode="HTML", reply_markup=_room_kb([], None, max_items))


async def _require_active(state: FSMContext, callback: CallbackQuery) -> dict | None:
    data = await state.get_data()
    if "sacrifice" not in data:
        await callback.answer("Сессия апгрейда истекла — начни заново: /upgrade", show_alert=True)
        return None
    return data


@router.callback_query(F.data == "upg:cancel")
async def cb_upgrade_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with contextlib.suppress(Exception):
        await callback.message.edit_text("Апгрейд отменён.")
    await callback.answer()


@router.callback_query(F.data == "upg:room")
async def cb_upgrade_room(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await _require_active(state, callback)
    if data is None:
        return
    max_items, *_ = await _get_upgrade_settings(session)
    text = await _room_text(session, data["sacrifice"], data.get("target_id"))
    with contextlib.suppress(Exception):
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=_room_kb(data["sacrifice"], data.get("target_id"), max_items)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("upg:add:"))
async def cb_upgrade_add(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await _require_active(state, callback)
    if data is None:
        return
    page = int(callback.data.split(":")[2])
    max_items, *_ = await _get_upgrade_settings(session)
    if len(data["sacrifice"]) >= max_items:
        await callback.answer(f"Максимум {max_items} карточек за раз.", show_alert=True)
        return

    owned = await _owned_cards_with_avail(session, callback.from_user.id, data["sacrifice"])
    if not owned:
        await callback.answer("Больше нечего добавить.", show_alert=True)
        return

    with contextlib.suppress(Exception):
        await callback.message.edit_text("Выбери карточку в ставку:", reply_markup=upgrade_add_picker_kb(owned, page))
    await callback.answer()


@router.callback_query(F.data.startswith("upg:additem:"))
async def cb_upgrade_additem(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await _require_active(state, callback)
    if data is None:
        return
    card_id = int(callback.data.split(":")[2])
    max_items, *_ = await _get_upgrade_settings(session)
    sacrifice = data["sacrifice"]
    if len(sacrifice) >= max_items:
        await callback.answer(f"Максимум {max_items} карточек.", show_alert=True)
        return

    already = sacrifice.count(card_id)
    owned = await _owned_qty(session, callback.from_user.id, card_id)
    if already >= owned:
        await callback.answer("Больше нет свободных копий этой карточки.", show_alert=True)
        return

    sacrifice.append(card_id)
    await state.update_data(sacrifice=sacrifice)

    owned_list = await _owned_cards_with_avail(session, callback.from_user.id, sacrifice)
    with contextlib.suppress(Exception):
        if owned_list and len(sacrifice) < max_items:
            await callback.message.edit_reply_markup(reply_markup=upgrade_add_picker_kb(owned_list, 0))
        else:
            await callback.message.edit_text("Добавлено ✅ Возвращайся в комнату апгрейда.", reply_markup=upgrade_add_picker_kb([], 0))
    await callback.answer("Добавлено ✅")


@router.callback_query(F.data.startswith("upg:remove:"))
async def cb_upgrade_remove(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await _require_active(state, callback)
    if data is None:
        return
    page = int(callback.data.split(":")[2])
    items = await _sacrifice_items(session, data["sacrifice"])
    if not items:
        await callback.answer("Ставка пуста.", show_alert=True)
        return
    with contextlib.suppress(Exception):
        await callback.message.edit_text(
            "Выбери карточку, чтобы убрать из ставки:", reply_markup=upgrade_remove_picker_kb(items, page)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("upg:removeitem:"))
async def cb_upgrade_removeitem(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await _require_active(state, callback)
    if data is None:
        return
    card_id = int(callback.data.split(":")[2])
    sacrifice = data["sacrifice"]
    if card_id in sacrifice:
        sacrifice.remove(card_id)
    await state.update_data(sacrifice=sacrifice)

    items = await _sacrifice_items(session, sacrifice)
    with contextlib.suppress(Exception):
        if items:
            await callback.message.edit_reply_markup(reply_markup=upgrade_remove_picker_kb(items, 0))
        else:
            await callback.message.edit_text("Ставка пуста.", reply_markup=upgrade_remove_picker_kb([], 0))
    await callback.answer("Убрано")


@router.callback_query(F.data.startswith("upg:target:"))
async def cb_upgrade_target(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await _require_active(state, callback)
    if data is None:
        return
    _, _, page_raw, rarity_filter = callback.data.split(":")
    page = int(page_raw)

    cards = [c for c in await list_active_cards(session) if c.rarity.upgrade_value > 0]
    if rarity_filter != "all":
        cards = [c for c in cards if c.rarity_id == rarity_filter]
    rarities = [r for r in await list_rarities(session) if r.upgrade_value > 0]

    with contextlib.suppress(Exception):
        await callback.message.edit_text(
            "Выбери карточку, которую хочешь получить:",
            reply_markup=upgrade_target_picker_kb(cards, page, rarity_filter, rarities),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("upg:settarget:"))
async def cb_upgrade_settarget(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await _require_active(state, callback)
    if data is None:
        return
    card_id = int(callback.data.split(":")[2])
    await state.update_data(target_id=card_id)

    max_items, *_ = await _get_upgrade_settings(session)
    sacrifice = data["sacrifice"]
    text = await _room_text(session, sacrifice, card_id)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_room_kb(sacrifice, card_id, max_items))
    await callback.answer("Цель выбрана 🎯")


@router.callback_query(F.data == "upg:spin")
async def cb_upgrade_spin(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await _require_active(state, callback)
    if data is None:
        return
    sacrifice = data.get("sacrifice") or []
    target_id = data.get("target_id")
    if not sacrifice or target_id is None:
        await callback.answer("Сначала выбери ставку и цель.", show_alert=True)
        return

    user = await get_or_create_user(session, callback.from_user)

    counts = Counter(sacrifice)
    for card_id, qty in counts.items():
        owned = await _owned_qty(session, user.id, card_id)
        if owned < qty:
            await state.clear()
            with contextlib.suppress(Exception):
                await callback.message.edit_text(
                    "⚠️ Состав ставки изменился (не хватает карточек) — апгрейд отменён. Начни заново: /upgrade"
                )
            await callback.answer()
            return

    target_card = await get_card(session, target_id)
    if target_card is None or target_card.rarity.upgrade_value <= 0:
        await callback.answer("Целевая карточка сейчас недоступна.", show_alert=True)
        return

    _, fairness, min_pct, max_pct = await _get_upgrade_settings(session)
    sac_items = await _sacrifice_items(session, sacrifice)
    sacrifice_value = sum(c.rarity.upgrade_value * qty for c, qty in sac_items)
    chance = _compute_chance(sacrifice_value, target_card.rarity.upgrade_value, fairness, min_pct, max_pct)

    success = random.random() < chance

    for card_id, qty in counts.items():
        uc = await session.get(UserCard, (user.id, card_id))
        if uc:
            uc.count -= qty
            if uc.count <= 0:
                await session.delete(uc)

    if success:
        now = datetime.now(timezone.utc)
        target_uc = await session.get(UserCard, (user.id, target_id))
        if target_uc is None:
            target_uc = UserCard(
                user_id=user.id, card_id=target_id, count=1, first_obtained_at=now, last_obtained_at=now,
                pulls_since_obtained=0,
            )
            session.add(target_uc)
        else:
            target_uc.count += 1
            target_uc.last_obtained_at = now
            target_uc.pulls_since_obtained = 0

    outcome = "успех" if success else "провал"
    log_event(
        session, "upgrade", user.id,
        f"{display_name(user)}: {outcome}, шанс {chance * 100:.1f}%, ставка {sacrifice_value:g} -> «{target_card.name}» ({target_card.rarity.upgrade_value:g})",
    )
    await session.commit()
    await state.clear()

    if success:
        result_text = (
            f"🎉 <b>Успех!</b>\n\nТы получил(а): {target_card.rarity.emoji_fallback} {escape(target_card.name)}\n"
            f"Шанс был: {chance * 100:.1f}%"
        )
    else:
        result_text = (
            f"💥 <b>Провал.</b>\n\nСтавка сгорела впустую.\nШанс был: {chance * 100:.1f}%\n\n"
            "Повезёт в другой раз — /upgrade"
        )

    with contextlib.suppress(Exception):
        await callback.message.edit_text(result_text, parse_mode="HTML")
    await callback.answer()

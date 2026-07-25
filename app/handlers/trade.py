import contextlib
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.activity_repo import log_event
from app.db.models import Trade
from app.db.trades_repo import (
    add_item,
    addable_cards,
    cancel_trade,
    create_trade,
    execute_trade,
    find_user_by_username,
    get_active_trade_for_user,
    get_trade,
    offered_items_by,
    remove_item,
)
from app.services.format import display_name as _display_name
from app.services.users import get_or_create_user
from app.keyboards.trade import (
    trade_add_picker_kb,
    trade_confirm_kb,
    trade_invite_kb,
    trade_pending_kb,
    trade_remove_picker_kb,
    trade_room_kb,
)

router = Router(name="trade")


def _fmt_items(items) -> str:
    if not items:
        return "— ничего —"
    return "\n".join(f"{i.card.rarity.emoji_fallback} {escape(i.card.name)} ×{i.qty}" for i in items)


def _room_text(trade: Trade, viewer_id: int) -> str:
    if viewer_id == trade.initiator_id:
        other, my_ready, other_ready = trade.counterparty, trade.ready_initiator, trade.ready_counterparty
    else:
        other, my_ready, other_ready = trade.initiator, trade.ready_counterparty, trade.ready_initiator

    other_name = _display_name(other)
    my_items = offered_items_by(trade, viewer_id)
    other_items = offered_items_by(trade, other.id)

    return (
        f"🔁 <b>Трейд с {other_name}</b>\n\n"
        f"Ты предлагаешь:\n{_fmt_items(my_items)}\n\n"
        f"{other_name} предлагает:\n{_fmt_items(other_items)}\n\n"
        f"Твой статус: {'✅ готов(а)' if my_ready else '⏳ выбираешь карточки'}\n"
        f"Статус {other_name}: {'✅ готов(а)' if other_ready else '⏳ выбирает карточки'}"
    )


def _confirm_text(trade: Trade, viewer_id: int) -> str:
    if viewer_id == trade.initiator_id:
        other, my_conf, other_conf = trade.counterparty, trade.ready_initiator, trade.ready_counterparty
    else:
        other, my_conf, other_conf = trade.initiator, trade.ready_counterparty, trade.ready_initiator

    other_name = _display_name(other)
    my_items = offered_items_by(trade, viewer_id)
    other_items = offered_items_by(trade, other.id)

    return (
        "🔁 <b>Финальное подтверждение</b>\n\n"
        f"Ты отдаёшь:\n{_fmt_items(my_items)}\n\n"
        f"Ты получаешь:\n{_fmt_items(other_items)}\n\n"
        f"Твоё подтверждение: {'✅' if my_conf else '⏳ ещё нет'}\n"
        f"Подтверждение {other_name}: {'✅' if other_conf else '⏳ ещё нет'}\n\n"
        "Обмен произойдёт только когда подтвердят оба."
    )


async def _push_room(bot: Bot, trade: Trade, viewer_id: int) -> None:
    msg_id = trade.room_msg_initiator if viewer_id == trade.initiator_id else trade.room_msg_counterparty
    if not msg_id:
        return
    my_ready = trade.ready_initiator if viewer_id == trade.initiator_id else trade.ready_counterparty
    with contextlib.suppress(Exception):
        await bot.edit_message_text(
            chat_id=viewer_id,
            message_id=msg_id,
            text=_room_text(trade, viewer_id),
            parse_mode="HTML",
            reply_markup=trade_room_kb(trade.id, my_ready),
        )


async def _push_confirm(bot: Bot, trade: Trade, viewer_id: int) -> None:
    msg_id = trade.room_msg_initiator if viewer_id == trade.initiator_id else trade.room_msg_counterparty
    if not msg_id:
        return
    with contextlib.suppress(Exception):
        await bot.edit_message_text(
            chat_id=viewer_id,
            message_id=msg_id,
            text=_confirm_text(trade, viewer_id),
            parse_mode="HTML",
            reply_markup=trade_confirm_kb(trade.id),
        )


def _is_participant(trade: Trade, user_id: int) -> bool:
    return user_id in (trade.initiator_id, trade.counterparty_id)


@router.message(Command("trade"))
async def cmd_trade(message: Message, session: AsyncSession, bot: Bot) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("@"):
        await message.answer("Использование: <code>/trade @username</code> — предложить обмен карточками.", parse_mode="HTML")
        return

    target_username = args[1].strip().lstrip("@")
    initiator = await get_or_create_user(session, message.from_user)

    if await get_active_trade_for_user(session, initiator.id):
        await message.answer("У тебя уже есть активный трейд. Заверши или отмени его, прежде чем начинать новый.")
        return

    target = await find_user_by_username(session, target_username)
    if target is None:
        await message.answer(f"Не нашёл пользователя @{target_username} — он должен хотя бы раз написать боту.")
        return
    if target.id == initiator.id:
        await message.answer("Нельзя предложить трейд самому себе.")
        return
    if await get_active_trade_for_user(session, target.id):
        await message.answer(f"@{target_username} сейчас уже участвует в другом трейде — попробуй позже.")
        return

    trade = await create_trade(session, initiator.id, target.id)
    initiator_name = _display_name(initiator)

    try:
        await bot.send_message(
            target.id,
            f"🔁 <b>{initiator_name}</b> предлагает тебе трейд карточками!",
            parse_mode="HTML",
            reply_markup=trade_invite_kb(trade.id),
        )
    except Exception:
        await cancel_trade(session, trade)
        await message.answer(f"Не получилось отправить предложение @{target_username} — возможно, он ещё не запускал бота или заблокировал его.")
        return

    log_event(session, "trade", initiator.id, f"{initiator_name} предложил(а) трейд @{target_username} (#{trade.id})")
    await session.commit()

    await message.answer(
        f"Предложение трейда отправлено @{target_username}. Жду ответа...",
        reply_markup=trade_pending_kb(trade.id),
    )


@router.callback_query(F.data.startswith("trade:accept:"))
async def cb_trade_accept(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    trade_id = int(callback.data.split(":")[2])
    trade = await get_trade(session, trade_id)
    if trade is None or trade.status != "pending" or callback.from_user.id != trade.counterparty_id:
        await callback.answer("Это предложение уже неактуально.", show_alert=True)
        return

    trade.status = "active"
    log_event(session, "trade", trade.counterparty_id, f"{_display_name(trade.counterparty)} принял(а) трейд с {_display_name(trade.initiator)} (#{trade.id})")
    await session.commit()

    with contextlib.suppress(Exception):
        await callback.message.edit_text("✅ Трейд начат!")

    msg_i = await bot.send_message(
        trade.initiator_id, _room_text(trade, trade.initiator_id), parse_mode="HTML",
        reply_markup=trade_room_kb(trade.id, trade.ready_initiator),
    )
    msg_c = await bot.send_message(
        trade.counterparty_id, _room_text(trade, trade.counterparty_id), parse_mode="HTML",
        reply_markup=trade_room_kb(trade.id, trade.ready_counterparty),
    )
    trade.room_msg_initiator = msg_i.message_id
    trade.room_msg_counterparty = msg_c.message_id
    await session.commit()
    await callback.answer()


@router.callback_query(F.data.startswith("trade:decline:"))
async def cb_trade_decline(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    trade_id = int(callback.data.split(":")[2])
    trade = await get_trade(session, trade_id)
    if trade is None or trade.status != "pending" or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Это предложение уже неактуально.", show_alert=True)
        return

    is_initiator = callback.from_user.id == trade.initiator_id
    action = "отменил(а) предложение" if is_initiator else "отклонил(а)"
    log_event(session, "trade", callback.from_user.id, f"{_display_name(trade.initiator if is_initiator else trade.counterparty)} {action} трейд (#{trade.id})")
    await cancel_trade(session, trade)
    with contextlib.suppress(Exception):
        await callback.message.edit_text("❌ Трейд отменён." if is_initiator else "❌ Трейд отклонён.")

    other_id = trade.counterparty_id if is_initiator else trade.initiator_id
    text = "❌ Собеседник отменил предложение трейда." if is_initiator else "❌ Собеседник отклонил трейд."
    with contextlib.suppress(Exception):
        await bot.send_message(other_id, text)
    await callback.answer()


@router.callback_query(F.data.startswith("trade:room:"))
async def cb_trade_room(callback: CallbackQuery, session: AsyncSession) -> None:
    trade_id = int(callback.data.split(":")[2])
    trade = await get_trade(session, trade_id)
    if trade is None or trade.status != "active" or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return
    my_ready = trade.ready_initiator if callback.from_user.id == trade.initiator_id else trade.ready_counterparty
    with contextlib.suppress(Exception):
        await callback.message.edit_text(
            _room_text(trade, callback.from_user.id), parse_mode="HTML", reply_markup=trade_room_kb(trade.id, my_ready)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("trade:add:"))
async def cb_trade_add(callback: CallbackQuery, session: AsyncSession) -> None:
    _, _, trade_id, page = callback.data.split(":")
    trade = await get_trade(session, int(trade_id))
    if trade is None or trade.status != "active" or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    cards = await addable_cards(session, trade, callback.from_user.id)
    if not cards:
        await callback.answer("У тебя нет карточек, которые можно добавить.", show_alert=True)
        return

    with contextlib.suppress(Exception):
        await callback.message.edit_text(
            "Выбери карточку, чтобы добавить в трейд (по одной за раз):",
            reply_markup=trade_add_picker_kb(trade.id, cards, int(page)),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("trade:additem:"))
async def cb_trade_additem(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    _, _, trade_id, card_id = callback.data.split(":")
    trade = await get_trade(session, int(trade_id))
    if trade is None or trade.status != "active" or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    ok = await add_item(session, trade, callback.from_user.id, int(card_id))
    if not ok:
        await callback.answer("Не осталось свободных копий этой карточки.", show_alert=True)
        return

    trade = await get_trade(session, trade.id)
    other_id = trade.counterparty_id if callback.from_user.id == trade.initiator_id else trade.initiator_id
    cards = await addable_cards(session, trade, callback.from_user.id)
    with contextlib.suppress(Exception):
        if cards:
            await callback.message.edit_reply_markup(reply_markup=trade_add_picker_kb(trade.id, cards, 0))
        else:
            await callback.message.edit_text("Больше нечего добавить.", reply_markup=trade_add_picker_kb(trade.id, [], 0))
    await _push_room(bot, trade, other_id)
    await callback.answer("Добавлено ✅")


@router.callback_query(F.data.startswith("trade:remove:"))
async def cb_trade_remove(callback: CallbackQuery, session: AsyncSession) -> None:
    _, _, trade_id, page = callback.data.split(":")
    trade = await get_trade(session, int(trade_id))
    if trade is None or trade.status != "active" or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    items = offered_items_by(trade, callback.from_user.id)
    if not items:
        await callback.answer("Ты пока ничего не предложил(а).", show_alert=True)
        return

    with contextlib.suppress(Exception):
        await callback.message.edit_text(
            "Выбери карточку, чтобы убрать её из трейда:",
            reply_markup=trade_remove_picker_kb(trade.id, items, int(page)),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("trade:removeitem:"))
async def cb_trade_removeitem(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    _, _, trade_id, card_id = callback.data.split(":")
    trade = await get_trade(session, int(trade_id))
    if trade is None or trade.status != "active" or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    await remove_item(session, trade, callback.from_user.id, int(card_id))
    trade = await get_trade(session, trade.id)
    other_id = trade.counterparty_id if callback.from_user.id == trade.initiator_id else trade.initiator_id
    items = offered_items_by(trade, callback.from_user.id)
    with contextlib.suppress(Exception):
        if items:
            await callback.message.edit_reply_markup(reply_markup=trade_remove_picker_kb(trade.id, items, 0))
        else:
            await callback.message.edit_text("Больше нечего убирать.", reply_markup=trade_remove_picker_kb(trade.id, [], 0))
    await _push_room(bot, trade, other_id)
    await callback.answer("Убрано")


@router.callback_query(F.data.startswith("trade:ready:"))
async def cb_trade_ready(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    trade_id = int(callback.data.split(":")[2])
    trade = await get_trade(session, trade_id)
    if trade is None or trade.status != "active" or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    if callback.from_user.id == trade.initiator_id:
        trade.ready_initiator = not trade.ready_initiator
    else:
        trade.ready_counterparty = not trade.ready_counterparty
    await session.commit()

    # Re-fetch after commit rather than trusting the pre-commit object in memory — if both
    # sides tap "ready" almost simultaneously, this is what lets whichever commit lands
    # second correctly observe that both flags are now set (SQLite serializes the writes,
    # so exactly one of the two concurrent handlers gets a true "both ready" here).
    trade = await get_trade(session, trade.id)

    if trade.ready_initiator and trade.ready_counterparty:
        trade.status = "confirming"
        trade.ready_initiator = False
        trade.ready_counterparty = False
        await session.commit()
        await _push_confirm(bot, trade, trade.initiator_id)
        await _push_confirm(bot, trade, trade.counterparty_id)
    else:
        await _push_room(bot, trade, trade.initiator_id)
        await _push_room(bot, trade, trade.counterparty_id)
    await callback.answer()


@router.callback_query(F.data.startswith("trade:confirm:"))
async def cb_trade_confirm(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    trade_id = int(callback.data.split(":")[2])
    trade = await get_trade(session, trade_id)
    if trade is None or trade.status != "confirming" or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    if callback.from_user.id == trade.initiator_id:
        trade.ready_initiator = True
    else:
        trade.ready_counterparty = True
    await session.commit()

    trade = await get_trade(session, trade.id)  # see note in cb_trade_ready about this re-fetch

    if trade.ready_initiator and trade.ready_counterparty:
        items_i = len(offered_items_by(trade, trade.initiator_id))
        items_c = len(offered_items_by(trade, trade.counterparty_id))
        log_event(
            session, "trade", trade.initiator_id,
            f"Обмен завершён между {_display_name(trade.initiator)} ({items_i} поз.) и "
            f"{_display_name(trade.counterparty)} ({items_c} поз.) (#{trade.id})",
        )
        await execute_trade(session, trade)
        done_text = "✅ Обмен совершён! Загляни в /mycards, чтобы увидеть обновлённую коллекцию."
        with contextlib.suppress(Exception):
            await bot.edit_message_text(chat_id=trade.initiator_id, message_id=trade.room_msg_initiator, text=done_text)
        with contextlib.suppress(Exception):
            await bot.edit_message_text(chat_id=trade.counterparty_id, message_id=trade.room_msg_counterparty, text=done_text)
        await callback.answer("Обмен завершён! 🎉")
    else:
        await _push_confirm(bot, trade, trade.initiator_id)
        await _push_confirm(bot, trade, trade.counterparty_id)
        await callback.answer("Подтверждено, ждём вторую сторону...")


@router.callback_query(F.data.startswith("trade:cancel:"))
async def cb_trade_cancel(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    trade_id = int(callback.data.split(":")[2])
    trade = await get_trade(session, trade_id)
    if trade is None or trade.status not in ("active", "confirming") or not _is_participant(trade, callback.from_user.id):
        await callback.answer("Недоступно.", show_alert=True)
        return

    canceller = trade.initiator if callback.from_user.id == trade.initiator_id else trade.counterparty
    log_event(session, "trade", callback.from_user.id, f"{_display_name(canceller)} отменил(а) трейд (#{trade.id})")
    await cancel_trade(session, trade)
    text = "❌ Трейд отменён."
    with contextlib.suppress(Exception):
        await bot.edit_message_text(chat_id=trade.initiator_id, message_id=trade.room_msg_initiator, text=text)
    with contextlib.suppress(Exception):
        await bot.edit_message_text(chat_id=trade.counterparty_id, message_id=trade.room_msg_counterparty, text=text)
    await callback.answer()

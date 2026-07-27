from aiogram.fsm.state import State, StatesGroup


class UpgradeFlow(StatesGroup):
    active = State()  # data: sacrifice (list[int] card ids, repeats allowed), target_id (int | None)

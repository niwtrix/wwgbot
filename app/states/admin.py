from aiogram.fsm.state import State, StatesGroup


class NewCard(StatesGroup):
    name = State()
    role = State()
    quote = State()
    telegram = State()
    youtube = State()
    twitch = State()
    rarity = State()
    photo = State()


class EditCardField(StatesGroup):
    waiting_value = State()  # data: card_id, field
    waiting_photo = State()  # data: card_id


class NewRarity(StatesGroup):
    name = State()
    weight = State()
    token_reward = State()


class EditRarityField(StatesGroup):
    waiting_value = State()  # data: rarity_id, field


class EditSetting(StatesGroup):
    waiting_value = State()  # data: key


class EmojiCapture(StatesGroup):
    waiting_emoji = State()


class NewCase(StatesGroup):
    name = State()
    price_tokens = State()


class EditCaseField(StatesGroup):
    waiting_value = State()  # data: case_id, field


class EditCaseOdds(StatesGroup):
    waiting_value = State()  # data: case_id, card_id, page, rarity_filter


class BroadcastMessage(StatesGroup):
    waiting_message = State()
    waiting_confirm = State()  # data: chat_id, message_id


class GrantTokens(StatesGroup):
    waiting_user = State()
    waiting_amount = State()  # data: target_id, target_label

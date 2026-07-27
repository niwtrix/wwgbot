from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Rarity(Base):
    __tablename__ = "rarities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # slug: common, rare, ...
    name: Mapped[str] = mapped_column(String(64))  # display name, e.g. "Редкая"
    weight: Mapped[float] = mapped_column(Float, default=10.0)  # relative pull chance
    token_reward: Mapped[int] = mapped_column(Integer, default=5)
    upgrade_value: Mapped[float] = mapped_column(Float, default=0.0)  # used only by /upgrade odds math
    emoji_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # custom_emoji_id
    emoji_fallback: Mapped[str] = mapped_column(String(16), default="🔹")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    case_only: Mapped[bool] = mapped_column(Boolean, default=False)  # excluded from normal rolls

    cards: Mapped[list["Card"]] = relationship(back_populates="rarity")


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(256), default="")
    quote: Mapped[str] = mapped_column(Text, default="")
    telegram_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    twitch_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    photo_file: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tg_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rarity_id: Mapped[str] = mapped_column(ForeignKey("rarities.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    rarity: Mapped["Rarity"] = relationship(back_populates="cards")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user id
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(256), default="")
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    last_pull_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    referred_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    hide_from_top: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_bonus_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserCard(Base):
    __tablename__ = "user_cards"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    first_obtained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_obtained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    pulls_since_obtained: Mapped[int] = mapped_column(Integer, default=0)  # dup-protection counter

    card: Mapped["Card"] = relationship()


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    price_tokens: Mapped[int] = mapped_column(Integer, default=100)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    odds: Mapped[list["CaseOdds"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    card_odds: Mapped[list["CaseCardOdds"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class CaseOdds(Base):
    """Legacy rarity-based case odds — superseded by CaseCardOdds (per-card weights).
    Kept only so old rows aren't silently dropped; no longer read by the draw logic."""

    __tablename__ = "case_odds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    rarity_id: Mapped[str] = mapped_column(ForeignKey("rarities.id"))
    weight: Mapped[float] = mapped_column(Float, default=100.0)

    case: Mapped["Case"] = relationship(back_populates="odds")
    rarity: Mapped["Rarity"] = relationship()


class CaseCardOdds(Base):
    __tablename__ = "case_card_odds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    weight: Mapped[float] = mapped_column(Float, default=100.0)

    case: Mapped["Case"] = relationship(back_populates="card_odds")
    card: Mapped["Card"] = relationship()


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    initiator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    counterparty_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    # pending (awaiting accept) -> active (picking cards) -> confirming (both readied,
    # final accept/reject) -> completed / cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending")
    ready_initiator: Mapped[bool] = mapped_column(Boolean, default=False)
    ready_counterparty: Mapped[bool] = mapped_column(Boolean, default=False)
    room_msg_initiator: Mapped[int | None] = mapped_column(Integer, nullable=True)
    room_msg_counterparty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    initiator: Mapped["User"] = relationship(foreign_keys=[initiator_id])
    counterparty: Mapped["User"] = relationship(foreign_keys=[counterparty_id])
    items: Mapped[list["TradeItem"]] = relationship(back_populates="trade", cascade="all, delete-orphan")


class ActivityLog(Base):
    __tablename__ = "activity_log"
    __table_args__ = (Index("ix_activity_log_type_created", "event_type", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminAccount(Base):
    """Web admin panel login — separate from the Telegram-side users/owners."""

    __tablename__ = "admin_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(64))
    password_salt: Mapped[str] = mapped_column(String(32))
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    can_cards: Mapped[bool] = mapped_column(Boolean, default=True)
    can_rarities: Mapped[bool] = mapped_column(Boolean, default=True)
    can_cases: Mapped[bool] = mapped_column(Boolean, default=True)
    can_settings: Mapped[bool] = mapped_column(Boolean, default=False)
    can_users: Mapped[bool] = mapped_column(Boolean, default=False)
    can_log: Mapped[bool] = mapped_column(Boolean, default=True)
    can_analytics: Mapped[bool] = mapped_column(Boolean, default=True)
    can_broadcast: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradeItem(Base):
    __tablename__ = "trade_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"))
    offered_by_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    qty: Mapped[int] = mapped_column(Integer, default=1)

    trade: Mapped["Trade"] = relationship(back_populates="items")
    card: Mapped["Card"] = relationship()

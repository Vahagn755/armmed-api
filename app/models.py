from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    total_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cases_solved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Գաղտնիություն. true դեպքում օգտատերը չի երևում ընդհանուր աղյուսակում
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    solved: Mapped[list["SolvedCase"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        # արագացնում է Top-50-ը և rank հաշվարկը
        Index("ix_users_leaderboard", "is_hidden", "total_score", "cases_solved"),
    )


class SolvedCase(Base):
    """Յուրաքանչյուր քեյսի համար միավոր տրվում է միայն մեկ անգամ (կանխում է «ֆարմինգը»)։"""

    __tablename__ = "solved_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    solved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="solved")

    __table_args__ = (UniqueConstraint("user_id", "case_id", name="uq_user_case"),)


class Purchase(Base):
    """Plus-ի գնում Telegram Stars-ով։ Plus ունի նա, ում telegram_id-ով առնվազն մեկ գրառում կա։"""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    charge_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)  # Telegram-ի վճարման id (կրկնությունից պաշտպանություն)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    plan: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 1m / 3m / 12m; NULL՝ հին «ընդմիշտ» գնում
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # NULL՝ առանց ժամկետի
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

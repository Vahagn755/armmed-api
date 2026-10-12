"""Plus-ի կարգավիճակ, սակագներ և անվճար/վճարովի քեյսերի բաժանում։"""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Purchase

FREE_PER_SPECIALTY = 5  # յուրաքանչյուր ուղղության առաջին 5 քեյսն անվճար են

# Սակագներ (աստղերով). env-ով կարելի է փոխել առանց կոդի։ PLUS_PRICE_STARS-ը հին անունն է՝ 1 ամսվա համար։
PRICE_1M = int(os.getenv("PLUS_PRICE_1M") or os.getenv("PLUS_PRICE_STARS") or "99")
PRICE_3M = int(os.getenv("PLUS_PRICE_3M") or "249")
PRICE_12M = int(os.getenv("PLUS_PRICE_12M") or "799")
PRICE_STARS = PRICE_1M  # համատեղելիության համար

PLANS = {
    "1m": {"days": 30, "stars": PRICE_1M, "recurring": True},    # Telegram Stars բաժանորդագրություն (30 օր)
    "3m": {"days": 90, "stars": PRICE_3M, "recurring": False},
    "12m": {"days": 365, "stars": PRICE_12M, "recurring": False},
}
SUBSCRIPTION_PERIOD = 2592000  # Telegram-ը թույլ է տալիս միայն 30 օր


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_plus_case(case_id: str) -> bool:
    try:
        return int(case_id.rsplit("_", 1)[1]) > FREE_PER_SPECIALTY
    except (IndexError, ValueError):
        return False


def plus_status(db: Session, telegram_id: int) -> dict:
    """{'active': bool, 'lifetime': bool, 'until': datetime|None}։"""
    rows = db.execute(select(Purchase.expires_at).where(Purchase.telegram_id == telegram_id)).all()
    now = now_utc()
    until = None
    for (exp,) in rows:
        if exp is None:
            return {"active": True, "lifetime": True, "until": None}
        exp = _utc(exp)
        if exp > now and (until is None or exp > until):
            until = exp
    return {"active": until is not None, "lifetime": False, "until": until}


def user_has_plus(db: Session, telegram_id: int) -> bool:
    return plus_status(db, telegram_id)["active"]


def record_purchase(db: Session, telegram_id: int, charge_id: str, stars: int,
                    plan: str | None = None, expires_at: datetime | None = None) -> bool:
    """True՝ եթե նոր գնում է գրանցվել, False՝ եթե արդեն կար։

    plan=None → հին «ընդմիշտ» գնում։ Մեկանգամյա 3m/12m գնումները գումարվում են ակտիվ ժամկետին։
    1m բաժանորդագրությունում expires_at-ը տալիս է Telegram-ը։
    """
    if db.scalar(select(Purchase.id).where(Purchase.charge_id == charge_id)):
        return False
    if plan in PLANS and expires_at is None:
        base = now_utc()
        st = plus_status(db, telegram_id)
        if st["until"] and st["until"] > base:
            base = st["until"]
        expires_at = base + timedelta(days=PLANS[plan]["days"])
    db.add(Purchase(telegram_id=telegram_id, charge_id=charge_id, stars=stars, plan=plan, expires_at=expires_at))
    db.commit()
    return True

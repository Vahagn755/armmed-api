"""Plus-ի կարգավիճակ և անվճար/վճարովի քեյսերի բաժանում։"""
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Purchase

FREE_PER_SPECIALTY = 5  # յուրաքանչյուր ուղղության առաջին 5 քեյսն անվճար են
PRICE_STARS = int(os.getenv("PLUS_PRICE_STARS", "99"))


def is_plus_case(case_id: str) -> bool:
    try:
        return int(case_id.rsplit("_", 1)[1]) > FREE_PER_SPECIALTY
    except (IndexError, ValueError):
        return False


def user_has_plus(db: Session, telegram_id: int) -> bool:
    return db.scalar(select(Purchase.id).where(Purchase.telegram_id == telegram_id).limit(1)) is not None


def record_purchase(db: Session, telegram_id: int, charge_id: str, stars: int) -> bool:
    """True՝ եթե նոր գնում է գրանցվել, False՝ եթե արդեն կար։"""
    if db.scalar(select(Purchase.id).where(Purchase.charge_id == charge_id)):
        return False
    db.add(Purchase(telegram_id=telegram_id, charge_id=charge_id, stars=stars))
    db.commit()
    return True

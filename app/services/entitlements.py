"""Plus-ի կարգավիճակ, սակագներ և անվճար/վճարովի քեյսերի բաժանում։"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Gift, LicPurchase, Purchase

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


LIC_FREE = int(os.getenv("LIC_FREE") or "50")            # լիցենզիայի ուղղության անվճար հարցերի քանակ
LIC_PRICE_STARS = int(os.getenv("LIC_PRICE_STARS") or "250")  # ≈ $4.99
LIC_SPECS = ("trauma", "family", "forensic", "ent", "pedsurg", "thoracic", "urology", "rehab", "pedrehab")


def lic_spec(case_id: str) -> str | None:
    """'licfamily_012' → 'family'; ոչ լիցենզիայի քեյսի համար՝ None։"""
    head = case_id.rsplit("_", 1)[0]
    if head.startswith("lic") and head[3:] in LIC_SPECS:
        return head[3:]
    return None


def is_plus_case(case_id: str) -> bool:
    try:
        n = int(case_id.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return False
    return n > (LIC_FREE if lic_spec(case_id) else FREE_PER_SPECIALTY)


def lic_owned(db: Session, telegram_id: int) -> list[str]:
    return list(db.scalars(select(LicPurchase.spec).where(LicPurchase.telegram_id == telegram_id)))


def has_case_access(db: Session, telegram_id: int, case_id: str) -> bool:
    """Անվճար քեյս, կամ Plus, կամ այդ ուղղության առանձին գնում։"""
    if not is_plus_case(case_id):
        return True
    if user_has_plus(db, telegram_id):
        return True
    sp = lic_spec(case_id)
    return bool(sp and sp in lic_owned(db, telegram_id))


def record_lic_purchase(db: Session, telegram_id: int, spec: str, charge_id: str, stars: int) -> bool:
    if spec not in LIC_SPECS or db.scalar(select(LicPurchase.id).where(LicPurchase.charge_id == charge_id)):
        return False
    if db.scalar(select(LicPurchase.id).where(LicPurchase.telegram_id == telegram_id, LicPurchase.spec == spec)):
        return False
    db.add(LicPurchase(telegram_id=telegram_id, spec=spec, charge_id=charge_id, stars=stars))
    db.commit()
    return True


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


# ---------- Նվերներ ----------
def create_gift(db: Session, buyer_id: int, plan: str, charge_id: str, stars: int):
    """(gift, new)։ Կրկնվող charge_id-ի դեպքում նոր նվեր չի ստեղծվում։"""
    existing = db.scalar(select(Gift).where(Gift.charge_id == charge_id))
    if existing:
        return existing, False
    g = Gift(code=secrets.token_urlsafe(9), plan=plan, buyer_id=buyer_id, charge_id=charge_id, stars=stars)
    db.add(g)
    db.commit()
    return g, True


def redeem_gift(db: Session, code: str, redeemer_id: int):
    """('ok'|'used'|'none', gift)։ Ատոմար. նույն նվերը չի կարող երկու անգամ ակտիվանալ։"""
    g = db.scalar(select(Gift).where(Gift.code == code))
    if not g:
        return "none", None
    res = db.execute(update(Gift).where(Gift.id == g.id, Gift.redeemed_by.is_(None))
                     .values(redeemed_by=redeemer_id, redeemed_at=now_utc()))
    db.commit()
    if res.rowcount != 1:
        return "used", g
    record_purchase(db, redeemer_id, f"gift-{g.code}", 0, plan=g.plan)
    return "ok", g


def list_gifts(db: Session, buyer_id: int):
    return list(db.scalars(select(Gift).where(Gift.buyer_id == buyer_id).order_by(Gift.id.desc()).limit(20)))

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import get_current_user
from ..services import entitlements as plus_svc
from .bot import tg_call

router = APIRouter(prefix="/api/plus", tags=["plus"])


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"is_plus": plus_svc.user_has_plus(db, user.telegram_id), "price_stars": plus_svc.PRICE_STARS,
            "free_per_specialty": plus_svc.FREE_PER_SPECIALTY}


@router.post("/invoice")
def invoice(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Ստեղծում է Telegram Stars (XTR) հաշիվ-հղում. հավելվածը բացում է այն tg.openInvoice-ով։"""
    if plus_svc.user_has_plus(db, user.telegram_id):
        return {"already": True}
    try:
        res = tg_call("createInvoiceLink", {
            "title": "QuizMD Plus",
            "description": "Բոլոր քեյսերը, նոր ուղղությունները, սխալների վրա աշխատանք և քննական ռեժիմ՝ ընդմիշտ։",
            "payload": f"plus:{user.telegram_id}",
            "provider_token": "",
            "currency": "XTR",
            "prices": [{"label": "QuizMD Plus", "amount": plus_svc.PRICE_STARS}],
        })
    except Exception:
        raise HTTPException(502, "Telegram invoice failed")
    return {"already": False, "link": res.get("result")}

import os

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import get_current_user
from ..services import entitlements as plus_svc
from .bot import tg_call

router = APIRouter(prefix="/api/plus", tags=["plus"])

PLAN_TITLES = {"1m": "QuizMD Plus · 1 ամիս", "3m": "QuizMD Plus · 3 ամիս", "12m": "QuizMD Plus · 12 ամիս"}


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    st = plus_svc.plus_status(db, user.telegram_id)
    return {
        "is_plus": st["active"],
        "lifetime": st["lifetime"],
        "until": st["until"].isoformat() if st["until"] else None,
        "price_stars": plus_svc.PRICE_1M,
        "plans": [{"id": k, "days": v["days"], "stars": v["stars"], "recurring": v["recurring"]} for k, v in plus_svc.PLANS.items()],
        "free_per_specialty": plus_svc.FREE_PER_SPECIALTY,
    }


@router.post("/invoice")
def invoice(body: dict = Body(default={}), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Ստեղծում է Telegram Stars (XTR) հաշիվ-հղում. հավելվածը բացում է այն tg.openInvoice-ով։"""
    plan = str(body.get("plan") or "1m")
    if plan not in plus_svc.PLANS:
        raise HTTPException(400, "unknown plan")
    st = plus_svc.plus_status(db, user.telegram_id)
    if st["lifetime"]:
        return {"already": True}
    cfg = plus_svc.PLANS[plan]
    payload = {
        "title": PLAN_TITLES[plan],
        "description": "Բոլոր քեյսերը, սխալների վրա աշխատանք, քննական ռեժիմ և նոր ուղղություններ։",
        "payload": f"plus:{user.telegram_id}:{plan}",
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": PLAN_TITLES[plan], "amount": cfg["stars"]}],
    }
    if cfg["recurring"]:
        payload["subscription_period"] = plus_svc.SUBSCRIPTION_PERIOD
    try:
        res = tg_call("createInvoiceLink", payload)
    except Exception:
        raise HTTPException(502, "Telegram invoice failed")
    return {"already": False, "link": res.get("result"), "plan": plan}


BOT_USERNAME = os.getenv("BOT_USERNAME", "ArmMedQuiz_bot")


def _gift_link(code: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=gift_{code}"


@router.post("/gift-invoice")
def gift_invoice(body: dict = Body(default={}), user: User = Depends(get_current_user)):
    """Նվերի հաշիվ (մեկանգամյա վճարում, առանց ավտոերկարացման)։"""
    plan = str(body.get("plan") or "3m")
    if plan not in plus_svc.PLANS:
        raise HTTPException(400, "unknown plan")
    cfg = plus_svc.PLANS[plan]
    try:
        res = tg_call("createInvoiceLink", {
            "title": "🎁 Նվեր՝ " + PLAN_TITLES[plan],
            "description": "Plus նվեր ընկերոջդ. վճարումից հետո կստանաս հղում, որը կարող ես ուղարկել նրան։",
            "payload": f"gift:{user.telegram_id}:{plan}",
            "provider_token": "",
            "currency": "XTR",
            "prices": [{"label": "🎁 " + PLAN_TITLES[plan], "amount": cfg["stars"]}],
        })
    except Exception:
        raise HTTPException(502, "Telegram invoice failed")
    return {"link": res.get("result"), "plan": plan}


@router.get("/gifts")
def my_gifts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"gifts": [
        {"code": g.code, "plan": g.plan, "link": _gift_link(g.code), "redeemed": g.redeemed_by is not None,
         "created_at": g.created_at.isoformat() if g.created_at else None}
        for g in plus_svc.list_gifts(db, user.telegram_id)
    ]}

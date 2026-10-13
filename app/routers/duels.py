"""Դուել ընկերոջ հետ։

Հոսքը. A-ն ընտրում է 5 անվճար քեյս → ստանում է հղում → ուղարկում է B-ին → երկուսն էլ լուծում են նույն քեյսերը →
սերվերը ինքն է հաշվում ճիշտ պատասխանների թիվը (client-ի ուղարկած «score»-ին չի վստահում)։
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Duel, User
from ..security import get_current_user
from ..services import entitlements as plus_svc

router = APIRouter(prefix="/api/duels", tags=["duels"])

N_CASES = 5
BOT_USERNAME = os.getenv("BOT_USERNAME", "ArmMedQuiz_bot")
MINIAPP_SHORT = os.getenv("MINIAPP_SHORT_NAME", "MED_Quiz")


class DuelCreate(BaseModel):
    case_ids: list[str] = Field(min_length=N_CASES, max_length=N_CASES)


class DuelResultIn(BaseModel):
    answers: list[int] = Field(min_length=N_CASES, max_length=N_CASES)  # ընտրված տարբերակի ինդեքսը՝ սկզբնական հերթականությամբ, -1՝ չպատասխանված
    time_sec: int = Field(ge=0, le=3600)


def _link(code: str) -> str:
    return f"https://t.me/{BOT_USERNAME}/{MINIAPP_SHORT}?startapp=duel_{code}"


def _get(db: Session, code: str) -> Duel:
    d = db.scalar(select(Duel).where(Duel.code == code))
    if d is None:
        raise HTTPException(404, "duel_not_found")
    return d


def _role(d: Duel, tid: int) -> str:
    if d.creator_id == tid:
        return "creator"
    if d.opp_id == tid:
        return "opponent"
    return "none"


def _winner(d: Duel) -> str | None:
    """'creator' | 'opponent' | 'draw' | None (երբ դեռ ոչ երկուսն են ավարտել)։"""
    if d.c_time is None or d.o_time is None:
        return None
    if d.c_score != d.o_score:
        return "creator" if d.c_score > d.o_score else "opponent"
    if d.c_time != d.o_time:
        return "creator" if d.c_time < d.o_time else "opponent"
    return "draw"


def _view(d: Duel, tid: int) -> dict:
    role = _role(d, tid)
    both = d.c_time is not None and d.o_time is not None
    w = _winner(d)
    mine_done = (d.c_time is not None) if role == "creator" else (d.o_time is not None)
    return {
        "code": d.code,
        "link": _link(d.code),
        "case_ids": d.case_ids.split(","),
        "role": role,
        "status": "waiting" if d.opp_id is None else ("done" if both else "playing"),
        "creator": {"name": d.creator_name, "done": d.c_time is not None,
                    "score": d.c_score if both else None, "time": d.c_time if both else None},
        "opponent": {"name": d.opp_name, "done": d.o_time is not None,
                     "score": d.o_score if both else None, "time": d.o_time if both else None},
        "my_done": mine_done,
        # «ես հաղթեցի» / «ես պարտվեցի» / «ոչ-ոքի»
        "result": None if w is None else ("draw" if w == "draw" else ("win" if w == role else "lose")),
    }


@router.post("")
def create_duel(body: DuelCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = body.case_ids
    if any(cid not in request.app.state.answer_key for cid in ids):
        raise HTTPException(400, "unknown_case")
    if len(set(ids)) != N_CASES:
        raise HTTPException(400, "duplicate_cases")
    for cid in ids:
        if "," in cid or plus_svc.is_plus_case(cid):
            raise HTTPException(400, "plus_case_not_allowed")  # որպեսզի երկու կողմն էլ կարողանան խաղալ
    d = Duel(code=secrets.token_urlsafe(6).replace("-", "a").replace("_", "b"), case_ids=",".join(ids),
             creator_id=user.telegram_id, creator_name=user.first_name or "")
    db.add(d)
    db.commit()
    return _view(d, user.telegram_id)


@router.get("/mine")
def my_duels(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tid = user.telegram_id
    rows = db.scalars(select(Duel).where(or_(Duel.creator_id == tid, Duel.opp_id == tid)).order_by(Duel.id.desc()).limit(20))
    out = []
    old = datetime.now(timezone.utc) - timedelta(days=1)
    for d in rows:
        ca = d.created_at if d.created_at is None or d.created_at.tzinfo else d.created_at.replace(tzinfo=timezone.utc)
        if d.opp_id is None and d.c_time is None and ca is not None and ca < old:
            continue  # 1 օրից հին, չսկսված դուելները չենք ցույց տալիս
        v = _view(d, tid)
        other = d.opp_name if v["role"] == "creator" else d.creator_name
        out.append({"code": d.code, "link": v["link"], "status": v["status"], "role": v["role"],
                    "my_done": v["my_done"], "result": v["result"], "other": other or "",
                    "creator": v["creator"], "opponent": v["opponent"]})
    return {"duels": out}


@router.get("/{code}")
def get_duel(code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _view(_get(db, code), user.telegram_id)


@router.post("/{code}/join")
def join_duel(code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = _get(db, code)
    tid = user.telegram_id
    if d.creator_id != tid:
        if d.opp_id is None:
            d.opp_id, d.opp_name = tid, user.first_name or ""
            db.commit()
        elif d.opp_id != tid:
            raise HTTPException(403, "duel_full")
    return _view(d, tid)


@router.post("/{code}/result")
def submit_result(code: str, body: DuelResultIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    d = _get(db, code)
    role = _role(d, user.telegram_id)
    if role == "none":
        raise HTTPException(403, "not_in_duel")
    if (role == "creator" and d.c_time is not None) or (role == "opponent" and d.o_time is not None):
        raise HTTPException(409, "already_submitted")
    key = request.app.state.answer_key
    ids = d.case_ids.split(",")
    score = sum(1 for cid, a in zip(ids, body.answers) if key.get(cid) == a)
    if role == "creator":
        d.c_score, d.c_time = score, body.time_sec
    else:
        d.o_score, d.o_time = score, body.time_sec
    db.commit()
    v = _view(d, user.telegram_id)
    v["my_score"] = score
    return v


@router.post("/{code}/share")
def share_duel(code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Պատրաստում է Telegram-ի «պատրաստի հաղորդագրություն» (Bot API 8.0), որպեսզի հավելվածը բացի ընկերների ընտրության ցանկը։"""
    from .bot import tg_call  # ուշ import՝ շրջանաձև կախվածությունից խուսափելու համար

    d = _get(db, code)
    if d.creator_id != user.telegram_id:
        raise HTTPException(403, "not_creator")
    link = _link(d.code)
    result = {
        "type": "article",
        "id": "duel_" + d.code,
        "title": "Դուել",
        "description": "5 բժշկական քեյս՝ ով ավելի շատ ճիշտ և արագ",
        "input_message_content": {
            "message_text": "⚔️ " + (user.first_name or "Ընկերդ") + "-ը քեզ դուելի է հրավիրում։\n5 բժշկական քեյս՝ հաղթում է ավելի շատ ճիշտ պատասխանողը, հավասարության դեպքում՝ ավելի արագը։",
        },
        "reply_markup": {"inline_keyboard": [[{"text": "⚔️ Ընդունել մարտահրավերը", "url": link}]]},
    }
    try:
        res = tg_call("savePreparedInlineMessage", {
            "user_id": user.telegram_id, "result": result,
            "allow_user_chats": True, "allow_group_chats": True,
            "allow_bot_chats": False, "allow_channel_chats": False,
        })
        mid = (res.get("result") or {}).get("id")
    except Exception:
        mid = None
    if not mid:
        raise HTTPException(502, "share_unavailable")
    return {"message_id": mid}


@router.delete("/{code}")
def delete_duel(code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Դուելը ջնջել կարող է միայն ստեղծողը, և միայն քանի դեռ այն ավարտված չէ։"""
    d = _get(db, code)
    if d.creator_id != user.telegram_id:
        raise HTTPException(403, "not_creator")
    if d.c_time is not None and d.o_time is not None:
        raise HTTPException(409, "duel_finished")
    db.delete(d)
    db.commit()
    return {"ok": True}

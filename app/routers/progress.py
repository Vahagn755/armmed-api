"""Առաջընթացի համաժամացում սարքերի միջև։ Սերվերը պահում է միայն թույլատրված դաշտերը, ստուգում է չափը,
իսկ միավորումը (merge) անում է հավելվածը՝ որպեսզի երկու սարքի տվյալները չկորչեն։"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Progress, User
from ..security import get_current_user

router = APIRouter(prefix="/api/progress", tags=["progress"])

ALLOWED = {"xp", "streak", "last", "done", "ach", "totalOk", "totalAns", "bestCombo",
           "duels", "duelWins", "perfect", "wrongSet", "ts"}
MAX_BYTES = 120_000


class ProgressIn(BaseModel):
    data: dict


@router.get("")
def get_progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.scalar(select(Progress).where(Progress.telegram_id == user.telegram_id))
    if row is None:
        return {"data": None, "updated_at": None}
    try:
        data = json.loads(row.data)
    except ValueError:
        data = None
    return {"data": data, "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.put("")
def put_progress(body: ProgressIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    clean = {k: v for k, v in body.data.items() if k in ALLOWED}
    raw = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise HTTPException(413, "progress_too_large")
    row = db.scalar(select(Progress).where(Progress.telegram_id == user.telegram_id))
    if row is None:
        db.add(Progress(telegram_id=user.telegram_id, data=raw))
    else:
        row.data = raw
    db.commit()
    return {"ok": True}

"""Ժամանակային աղյուսակներ (օր / շաբաթ / ամիս / տարի). միավորները հաշվվում են միայն այդ ժամանակահատվածում նոր լուծված քեյսերից։"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import SolvedCase, User
from ..security import get_current_user

router = APIRouter(prefix="/api/league", tags=["league"])


def period_bounds(tz_name: str, period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    """(սկիզբ, ավարտ) ընտրված ժամանակահատվածի՝ Երևանի ժամանակով։ period՝ day | week | month | year"""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:  # tzdata չկա → Երևանի ֆիքսված UTC+4
        tz = timezone(timedelta(hours=4))
    n = (now or datetime.now(timezone.utc)).astimezone(tz)
    day0 = n.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        return day0, day0 + timedelta(days=1)
    if period == "month":
        start = day0.replace(day=1)
        nxt = (start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1))
        return start, nxt
    if period == "year":
        start = day0.replace(month=1, day=1)
        return start, start.replace(year=start.year + 1)
    start = day0 - timedelta(days=n.weekday())  # week
    return start, start + timedelta(days=7)


def week_bounds(tz_name: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    return period_bounds(tz_name, "week", now)


def _top(db: Session, user: User, period: str) -> dict:
    start, end = period_bounds(get_settings().timezone, period)
    pts = func.sum(SolvedCase.points).label("pts")
    cnt = func.count(SolvedCase.id).label("cnt")
    rows = db.execute(
        select(User.id, User.first_name, pts, cnt)
        .join(User, User.id == SolvedCase.user_id)
        .where(SolvedCase.solved_at >= start, User.is_hidden.is_(False))
        .group_by(User.id, User.first_name)
        .order_by(pts.desc(), User.id.asc())
        .limit(50)
    ).all()
    players = [
        {"rank": i, "name": r.first_name or "Անանուն", "points": int(r.pts), "cases": int(r.cnt), "is_me": r.id == user.id}
        for i, r in enumerate(rows, start=1)
    ]
    mine = db.scalar(select(func.coalesce(func.sum(SolvedCase.points), 0)).where(
        SolvedCase.user_id == user.id, SolvedCase.solved_at >= start)) or 0
    rank = None
    if mine > 0:
        ahead_q = (
            select(SolvedCase.user_id)
            .join(User, User.id == SolvedCase.user_id)
            .where(SolvedCase.solved_at >= start, User.is_hidden.is_(False), SolvedCase.user_id != user.id)
            .group_by(SolvedCase.user_id)
            .having(func.sum(SolvedCase.points) > mine)
        )
        rank = (db.scalar(select(func.count()).select_from(ahead_q.subquery())) or 0) + 1
    return {"period": period, "ends_at": end.astimezone(timezone.utc).isoformat(), "week_ends_at": end.astimezone(timezone.utc).isoformat(), "players": players,
            "me": {"points": int(mine), "rank": rank}}


@router.get("/top")
def top(period: str = Query("week", pattern="^(day|week|month|year)$"),
        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _top(db, user, period)


@router.get("/week")
def week_top(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _top(db, user, "week")

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import MyStats, PlayerRow, TopResponse, VisibilityIn
from ..security import get_current_user
from ..services import leaderboard as lb

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


def _my_stats(db: Session, user: User) -> MyStats:
    return MyStats(
        rank=lb.get_rank(db, user),
        total_players=lb.total_players(db),
        first_name=user.first_name,
        username=user.username,
        total_score=user.total_score,
        cases_solved=user.cases_solved,
        streak_days=user.streak_days,
        is_hidden=user.is_hidden,
    )


@router.get("/top", response_model=TopResponse)
def top_players(
    limit: int = Query(50, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Լավագույն 50 խաղացողները + ընթացիկ օգտատիրոջ դիրքը։"""
    rows = lb.get_top(db, limit)
    players = [
        PlayerRow(
            rank=i,
            name=u.first_name or "Անանուն",
            username=u.username,
            total_score=u.total_score,
            cases_solved=u.cases_solved,
            streak_days=u.streak_days,
            is_me=(u.id == user.id),
        )
        for i, u in enumerate(rows, start=1)
    ]
    return TopResponse(
        updated_at=datetime.now(timezone.utc),
        total_players=lb.total_players(db),
        players=players,
        me=_my_stats(db, user),
    )


@router.get("/me", response_model=MyStats)
def my_rank(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """«Դիրք #42՝ 1500 խաղացողից» + անձնական վիճակագրություն։"""
    return _my_stats(db, user)


@router.patch("/me/visibility", response_model=MyStats)
def set_visibility(body: VisibilityIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Թույլ է տալիս օգտատիրոջը թաքնվել ընդհանուր աղյուսակից։"""
    user.is_hidden = body.is_hidden
    db.commit()
    return _my_stats(db, user)

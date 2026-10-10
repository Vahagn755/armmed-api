from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..models import User
from ..schemas import AnswerIn, AnswerOut
from ..security import get_current_user
from ..services import leaderboard as lb
from ..services.scoring import UnknownCase, submit_answer

router = APIRouter(prefix="/api/score", tags=["score"])


@router.post("/answer", response_model=AnswerOut)
def answer(
    body: AnswerIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Ստանում է քեյսի id-ն և ընտրված տարբերակի ինդեքսը (JSON-ի սկզբնական հերթականությամբ)։
    Ճիշտությունը ստուգվում է սերվերում, միավորը տրվում է քեյսի համար առավելագույնը մեկ անգամ։"""
    try:
        res = submit_answer(
            db, user, body.case_id, body.selected_index,
            request.app.state.answer_key, settings.points_per_case, settings.timezone,
        )
    except UnknownCase:
        raise HTTPException(404, "Unknown case_id")
    return AnswerOut(
        correct=res.correct,
        already_solved=res.already_solved,
        points_awarded=res.points_awarded,
        total_score=user.total_score,
        cases_solved=user.cases_solved,
        streak_days=user.streak_days,
        rank=lb.get_rank(db, user),
        total_players=lb.total_players(db),
    )

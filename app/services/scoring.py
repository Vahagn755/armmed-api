from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import SolvedCase, User


class UnknownCase(Exception):
    pass


@dataclass
class AnswerResult:
    correct: bool
    already_solved: bool
    points_awarded: int


def today(tz_name: str) -> date:
    """Առանձին ֆունկցիա, որպեսզի թեստերում հնարավոր լինի ժամանակը փոխել։"""
    return datetime.now(ZoneInfo(tz_name)).date()


def _touch_streak(user: User, current_day: date) -> None:
    if user.last_active_date == current_day:
        return
    if user.last_active_date == current_day - timedelta(days=1):
        user.streak_days += 1
    else:
        user.streak_days = 1
    user.last_active_date = current_day


def submit_answer(
    db: Session,
    user: User,
    case_id: str,
    selected_index: int,
    answer_key: dict[str, int],
    points_per_case: int,
    tz_name: str,
) -> AnswerResult:
    if case_id not in answer_key:
        raise UnknownCase(case_id)

    correct = selected_index == answer_key[case_id]
    _touch_streak(user, today(tz_name))  # ցանկացած պատասխան = օրվա ակտիվություն

    already = db.scalar(select(SolvedCase.id).where(SolvedCase.user_id == user.id, SolvedCase.case_id == case_id))
    awarded = 0

    if correct and already is None:
        try:
            db.add(SolvedCase(user_id=user.id, case_id=case_id, points=points_per_case))
            db.flush()  # UNIQUE (user_id, case_id) պաշտպանում է զուգահեռ հարցումներից
            # ատոմար թարմացում՝ lost-update-ից խուսափելու համար
            db.execute(
                update(User)
                .where(User.id == user.id)
                .values(total_score=User.total_score + points_per_case, cases_solved=User.cases_solved + 1)
            )
            awarded = points_per_case
        except IntegrityError:
            db.rollback()
            already = 1
            _touch_streak(user, today(tz_name))

    db.commit()
    db.refresh(user)
    return AnswerResult(correct=correct, already_solved=already is not None, points_awarded=awarded)

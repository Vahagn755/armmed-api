from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import User

# Դասակարգման կարգը (միշտ նույնը Top-ի և Rank-ի համար).
# 1) ավելի շատ միավոր, 2) ավելի շատ լուծված քեյս, 3) ավելի շուտ գրանցված (փոքր id)
_ORDER = (User.total_score.desc(), User.cases_solved.desc(), User.id.asc())


def total_players(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).where(User.is_hidden.is_(False))) or 0


def get_top(db: Session, limit: int = 50) -> list[User]:
    return list(db.scalars(select(User).where(User.is_hidden.is_(False)).order_by(*_ORDER).limit(limit)))


def get_rank(db: Session, user: User) -> int:
    """1 + այն տեսանելի խաղացողների թիվը, ովքեր դասակարգման մեջ ավելի բարձր են։"""
    ahead = db.scalar(
        select(func.count(User.id)).where(
            User.is_hidden.is_(False),
            User.id != user.id,
            or_(
                User.total_score > user.total_score,
                and_(User.total_score == user.total_score, User.cases_solved > user.cases_solved),
                and_(
                    User.total_score == user.total_score,
                    User.cases_solved == user.cases_solved,
                    User.id < user.id,
                ),
            ),
        )
    )
    return (ahead or 0) + 1

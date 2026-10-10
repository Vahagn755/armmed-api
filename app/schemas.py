from datetime import datetime

from pydantic import BaseModel, Field


class PlayerRow(BaseModel):
    rank: int
    name: str
    username: str | None
    total_score: int
    cases_solved: int
    streak_days: int
    is_me: bool = False


class MyStats(BaseModel):
    rank: int
    total_players: int
    first_name: str
    username: str | None
    total_score: int
    cases_solved: int
    streak_days: int
    is_hidden: bool


class TopResponse(BaseModel):
    updated_at: datetime
    total_players: int
    players: list[PlayerRow]
    me: MyStats


class AnswerIn(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)
    selected_index: int = Field(ge=0, le=9)


class AnswerOut(BaseModel):
    correct: bool
    already_solved: bool
    points_awarded: int
    total_score: int
    cases_solved: int
    streak_days: int
    rank: int
    total_players: int


class VisibilityIn(BaseModel):
    is_hidden: bool

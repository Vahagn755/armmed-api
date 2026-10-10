"""Կարգավորումներ՝ միայն միջավայրի փոփոխականներից (ոչ մի գաղտնիք կոդի մեջ)։"""
import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    cors_origins: list[str]
    points_per_case: int
    timezone: str
    initdata_max_age: int
    cases_dir: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        bot_token=os.environ["BOT_TOKEN"],  # պարտադիր է
        database_url=os.getenv("DATABASE_URL", "sqlite:///./quiz.db"),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
        points_per_case=int(os.getenv("POINTS_PER_CASE", "10")),
        timezone=os.getenv("TIMEZONE", "Asia/Yerevan"),
        initdata_max_age=int(os.getenv("INITDATA_MAX_AGE_SECONDS", "86400")),
        cases_dir=os.getenv("CASES_DIR", "cases"),
    )

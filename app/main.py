from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .cases import load_answer_key
from .config import get_settings
from .database import Base, engine
from .routers import bot, duels, leaderboard, league, plus, score


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(bind=engine)  # արտադրության մեջ՝ Alembic միգրացիաներ
    if engine.dialect.name == "postgresql":  # Stars-ի charge_id-ն 128 նիշից երկար է լինում + նոր սյուներ
        for stmt in (
            "ALTER TABLE purchases ALTER COLUMN charge_id TYPE VARCHAR(255)",
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS plan VARCHAR(16)",
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",
        ):
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(stmt)
            except Exception:
                pass
    app.state.answer_key = load_answer_key(settings.cases_dir)
    bot.register_webhook()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ARMMEDQUIZBOT Leaderboard", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(leaderboard.router)
    app.include_router(score.router)
    app.include_router(plus.router)
    app.include_router(duels.router)
    app.include_router(league.router)
    app.include_router(bot.router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()

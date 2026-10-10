from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .cases import load_answer_key
from .config import get_settings
from .database import Base, engine
from .routers import bot, leaderboard, plus, score


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(bind=engine)  # արտադրության մեջ՝ Alembic միգրացիաներ
    app.state.answer_key = load_answer_key(settings.cases_dir)
    bot.register_webhook()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ARMMEDQUIZBOT Leaderboard", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(leaderboard.router)
    app.include_router(score.router)
    app.include_router(plus.router)
    app.include_router(bot.router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()

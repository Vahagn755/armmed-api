"""Telegram Mini App-ի initData-ի վավերացում (HMAC-SHA256)։

Առանց սրա ցանկացած մարդ կարող է ուղարկել կեղծ telegram_id և ավելացնել ուրիշի միավորները։
Հղում՝ https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import User


class InvalidInitData(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age: int, now: float | None = None) -> dict:
    """Վերադարձնում է Telegram-ի user dict-ը, կամ բարձրացնում է InvalidInitData։"""
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise InvalidInitData("bad signature")

    try:
        auth_date = int(pairs["auth_date"])
    except (KeyError, ValueError):
        raise InvalidInitData("missing auth_date")
    if (now if now is not None else time.time()) - auth_date > max_age:
        raise InvalidInitData("initData expired")

    try:
        user = json.loads(pairs["user"])
        int(user["id"])
    except (KeyError, ValueError, TypeError):
        raise InvalidInitData("missing user")
    return user


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Սպասում է `Authorization: tma <initData>` header։ Ստեղծում/թարմացնում է օգտատիրոջը։"""
    scheme, _, init_data = authorization.partition(" ")
    if scheme.lower() != "tma" or not init_data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Telegram initData")
    try:
        tg_user = validate_init_data(init_data, settings.bot_token, settings.initdata_max_age)
    except InvalidInitData as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid initData: {e}")

    tg_id = int(tg_user["id"])
    user = db.scalar(select(User).where(User.telegram_id == tg_id))
    first_name = (tg_user.get("first_name") or "")[:128]
    username = (tg_user.get("username") or None)
    if user is None:
        user = User(telegram_id=tg_id, first_name=first_name, username=username)
        db.add(user)
    else:
        user.first_name, user.username = first_name, username
    db.commit()
    return user

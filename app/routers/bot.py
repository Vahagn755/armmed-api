"""Telegram-բոտի ողջույնը՝ /start-ին պատասխանում է հաղորդագրությամբ և «Բացել» կոճակով։

Webhook-ը գրանցվում է ինքնաբերաբար սերվերի մեկնարկի ժամանակ (setWebhook)։
"""
import hashlib
import hmac
import json
import logging
import os
import threading
import urllib.request

from fastapi import APIRouter, Header, HTTPException, Request

from ..config import get_settings

log = logging.getLogger("bot")
router = APIRouter()

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://vahagn755.github.io/QUIZ-ARMMED/app_v10.html")
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://armmed-api.onrender.com")

WELCOME = (
    "Բարև! Սա ARMMEDQUIZBOT-ն է 🩺\n"
    "Բժշկական քեյս-քվիզներ ուսանողների և բժիշկների համար. սրտաբանություն, նյարդաբանություն, "
    "թոքաբանություն, շտապ օգնություն և այլ ուղղություններ։\n\n"
    "Սեղմիր «Բացել քվիզը» կոճակը ներքևում՝ կամ ընտրացանկի կոճակը այս չաթի ներքևում։"
)


def _secret() -> str:
    # webhook-ի գաղտնի նշան՝ ստացվում է բոտի token-ից (նոր env փոփոխական պետք չէ)
    return hashlib.sha256(("wh:" + get_settings().bot_token).encode()).hexdigest()[:48]


def _call(method: str, payload: dict) -> None:
    url = f"https://api.telegram.org/bot{get_settings().bot_token}/{method}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()


def register_webhook() -> None:
    def run():
        try:
            _call("setWebhook", {
                "url": PUBLIC_URL.rstrip("/") + "/telegram/webhook",
                "secret_token": _secret(),
                "allowed_updates": ["message"],
            })
            log.info("Telegram webhook registered")
        except Exception as e:  # սերվերը չպետք է ընկնի
            log.warning("setWebhook failed: %s", e)
    threading.Thread(target=run, daemon=True).start()


@router.post("/telegram/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    if not hmac.compare_digest(x_telegram_bot_api_secret_token, _secret()):
        raise HTTPException(403, "forbidden")
    update = await request.json()
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat = (msg.get("chat") or {}).get("id")
    if chat and msg.get("chat", {}).get("type") == "private" and text.startswith("/start"):
        try:
            _call("sendMessage", {
                "chat_id": chat,
                "text": WELCOME,
                "reply_markup": {"inline_keyboard": [[{"text": "🩺 Բացել քվիզը", "web_app": {"url": WEBAPP_URL}}]]},
            })
        except Exception as e:
            log.warning("sendMessage failed: %s", e)
    return {"ok": True}

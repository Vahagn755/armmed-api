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

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://vahagn755.github.io/QUIZ-ARMMED/app_v15.html")
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


def tg_call(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{get_settings().bot_token}/{method}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode() or "{}")


_call = tg_call


def register_webhook() -> None:
    def run():
        try:
            _call("setWebhook", {
                "url": PUBLIC_URL.rstrip("/") + "/telegram/webhook",
                "secret_token": _secret(),
                "allowed_updates": ["message", "pre_checkout_query"],
            })
            log.info("Telegram webhook registered")
        except Exception as e:  # սերվերը չպետք է ընկնի
            log.warning("setWebhook failed: %s", e)
    threading.Thread(target=run, daemon=True).start()


def _parse_payload(payload: str, payer):
    """'plus:{id}' (հին) կամ 'plus:{id}:{plan}' → (id, plan|None); սխալ դեպքում՝ None։"""
    from ..services.entitlements import PLANS
    parts = payload.split(":")
    if len(parts) < 2 or parts[0] != "plus" or not payer or parts[1] != str(payer):
        return None
    if len(parts) == 2:
        return (parts[1], None)
    return (parts[1], parts[2]) if parts[2] in PLANS else None


@router.post("/telegram/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    if not hmac.compare_digest(x_telegram_bot_api_secret_token, _secret()):
        raise HTTPException(403, "forbidden")
    update = await request.json()

    pcq = update.get("pre_checkout_query")
    if pcq:  # Stars վճարումից առաջ պետք է հաստատել 10 վայրկյանում
        payer = (pcq.get("from") or {}).get("id")
        parsed = _parse_payload(str(pcq.get("invoice_payload", "")), payer)
        ok = parsed is not None and pcq.get("currency") == "XTR"
        try:
            payload = {"pre_checkout_query_id": pcq["id"], "ok": ok}
            if not ok:
                payload["error_message"] = "Վճարումը չի կարող կատարվել"
            _call("answerPreCheckoutQuery", payload)
        except Exception as e:
            log.warning("answerPreCheckoutQuery failed: %s", e)
        return {"ok": True}

    msg = update.get("message") or {}
    sp = msg.get("successful_payment")
    if sp and sp.get("currency") == "XTR":
        payer = (msg.get("from") or {}).get("id")
        parsed = _parse_payload(str(sp.get("invoice_payload", "")), payer)
        if payer and parsed is not None:
            from datetime import datetime, timezone
            from ..database import SessionLocal
            from ..services.entitlements import record_purchase
            plan = parsed[1]
            exp = None
            if sp.get("subscription_expiration_date"):
                exp = datetime.fromtimestamp(int(sp["subscription_expiration_date"]), tz=timezone.utc)
            db = SessionLocal()
            try:
                new = record_purchase(db, int(payer), str(sp.get("telegram_payment_charge_id")),
                                      int(sp.get("total_amount", 0)), plan=plan, expires_at=exp)
            finally:
                db.close()
            renewal = bool(sp.get("is_recurring")) and not sp.get("is_first_recurring")
            if new and not renewal:
                try:
                    _call("sendMessage", {"chat_id": msg["chat"]["id"], "text": "✅ Շնորհակալություն։ QuizMD Plus-ը միացված է։ Բացիր քվիզը և շարունակիր 🩺"})
                except Exception as e:
                    log.warning("thanks failed: %s", e)
        return {"ok": True}

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

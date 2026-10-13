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

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://vahagn755.github.io/QUIZ-ARMMED/app_v23.html")
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


def _parse_gift_payload(payload: str, payer):
    """'gift:{buyer_id}:{plan}' → plan | None։"""
    from ..services.entitlements import PLANS
    parts = payload.split(":")
    if len(parts) == 3 and parts[0] == "gift" and payer and parts[1] == str(payer) and parts[2] in PLANS:
        return parts[2]
    return None


PLAN_LABEL = {"1m": "1 ամիս", "3m": "3 ամիս", "12m": "12 ամիս"}
BOT_USERNAME = os.getenv("BOT_USERNAME", "ArmMedQuiz_bot")


def _open_btn():
    return {"inline_keyboard": [[{"text": "🩺 Բացել քվիզը", "web_app": {"url": WEBAPP_URL}}]]}


def _handle_gift_start(chat: int, user_id: int, code: str) -> None:
    from ..database import SessionLocal
    from ..services.entitlements import redeem_gift
    db = SessionLocal()
    try:
        status, g = redeem_gift(db, code, int(user_id))
        buyer, plan = (g.buyer_id, g.plan) if g else (None, None)
    finally:
        db.close()
    try:
        if status == "ok":
            _call("sendMessage", {"chat_id": chat, "reply_markup": _open_btn(),
                                  "text": f"🎁 Դու նվեր ստացար՝ QuizMD Plus {PLAN_LABEL.get(plan, '')}։ Բոլոր քեյսերը բաց են։ Բարի ուսում 🩺"})
            if buyer and int(buyer) != int(user_id):
                try:
                    _call("sendMessage", {"chat_id": buyer, "text": "🎉 Քո նվերն ընդունվեց։ Շնորհակալություն, որ կիսվեցիր։"})
                except Exception as e:
                    log.warning("buyer notify failed: %s", e)
        elif status == "used":
            _call("sendMessage", {"chat_id": chat, "text": "Այս նվերն արդեն օգտագործվել է։"})
        else:
            _call("sendMessage", {"chat_id": chat, "text": "Նվերի հղումը սխալ է կամ չի գտնվել։"})
    except Exception as e:
        log.warning("gift start reply failed: %s", e)


@router.post("/telegram/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    if not hmac.compare_digest(x_telegram_bot_api_secret_token, _secret()):
        raise HTTPException(403, "forbidden")
    update = await request.json()

    pcq = update.get("pre_checkout_query")
    if pcq:  # Stars վճարումից առաջ պետք է հաստատել 10 վայրկյանում
        payer = (pcq.get("from") or {}).get("id")
        ipl = str(pcq.get("invoice_payload", ""))
        ok = (_parse_payload(ipl, payer) is not None or _parse_gift_payload(ipl, payer) is not None) and pcq.get("currency") == "XTR"
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
        gplan = _parse_gift_payload(str(sp.get("invoice_payload", "")), payer)
        if gplan:
            from ..database import SessionLocal
            from ..services.entitlements import create_gift
            db = SessionLocal()
            try:
                g, new = create_gift(db, int(payer), gplan, str(sp.get("telegram_payment_charge_id")), int(sp.get("total_amount", 0)))
                code = g.code
            finally:
                db.close()
            if new:
                link = f"https://t.me/{BOT_USERNAME}?start=gift_{code}"
                from urllib.parse import urlencode
                share = "https://t.me/share/url?" + urlencode({"url": link, "text": "🎁 Նվեր քեզ՝ QuizMD Plus!"})
                try:
                    _call("sendMessage", {
                        "chat_id": msg["chat"]["id"],
                        "text": f"🎁 Նվերդ պատրաստ է՝ QuizMD Plus {PLAN_LABEL.get(gplan, '')}։\nՈւղարկիր այս հղումը ընկերոջդ. երբ նա բացի այն, Plus-ը կմիանա իր հաշվին։\n\n{link}",
                        "reply_markup": {"inline_keyboard": [[{"text": "📤 Ուղարկել ընկերոջը", "url": share}]]},
                    })
                except Exception as e:
                    log.warning("gift msg failed: %s", e)
            return {"ok": True}
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
        arg = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
        uid = (msg.get("from") or {}).get("id")
        if arg.startswith("gift_") and uid:
            _handle_gift_start(chat, uid, arg[5:])
            return {"ok": True}
        try:
            _call("sendMessage", {
                "chat_id": chat,
                "text": WELCOME,
                "reply_markup": {"inline_keyboard": [[{"text": "🩺 Բացել քվիզը", "web_app": {"url": WEBAPP_URL}}]]},
            })
        except Exception as e:
            log.warning("sendMessage failed: %s", e)
    return {"ok": True}

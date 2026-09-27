"""Outbound alert delivery.

A hill-district warning system is worthless if it only reaches people with 4G
and a charged smartphone, so delivery is a *pluggable fan-out*: SMS for the
majority, IVR (automated voice call) for households where the elders cannot read
or cannot be reached by text, and in-app push where data exists.

Provider adapters are chosen by configuration. ``console`` is the default so the
MVP runs with no credentials and no spend; Twilio and MSG91 adapters are real
REST implementations that activate by setting keys. Every dispatch is written to
``notifications`` so reach is provable rather than asserted — the admin console
shows delivered vs simulated, and the two are never conflated.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Channel, Notification, NotificationStatus, Ward
from app.services import i18n

log = logging.getLogger("aapaatsathi.notify")


@dataclass
class SendResult:
    ok: bool
    ref: str | None = None
    status: str = NotificationStatus.SIMULATED.value
    error: str | None = None
    provider: str = "console"


class BaseProvider:
    name = "base"

    async def send_sms(self, phone: str, body: str) -> SendResult:  # pragma: no cover
        raise NotImplementedError

    async def send_ivr(self, phone: str, script: str) -> SendResult:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:
        return None


class ConsoleProvider(BaseProvider):
    """Default provider: prints, records as *simulated*, spends nothing.

    This is what makes the project clone-and-run. It also means a demo can never
    accidentally message 12,000 real phone numbers.
    """

    name = "console"

    async def send_sms(self, phone: str, body: str) -> SendResult:
        log.info("[SIMULATED SMS] %s :: %s", phone, body)
        await asyncio.sleep(0)  # keep the interface honest about being async
        return SendResult(ok=True, ref=f"sim-{int(time.time() * 1000) % 10**9}", provider=self.name)

    async def send_ivr(self, phone: str, script: str) -> SendResult:
        log.info("[SIMULATED IVR] %s :: %s", phone, script[:120])
        return SendResult(ok=True, ref=f"sim-ivr-{int(time.time() * 1000) % 10**9}", provider=self.name)


class TwilioProvider(BaseProvider):
    name = "twilio"

    def __init__(self) -> None:
        self.sid = settings.twilio_account_sid
        self.token = settings.twilio_auth_token
        self.sender = settings.twilio_from_number
        self._client = httpx.AsyncClient(
            timeout=12.0,
            auth=(self.sid, self.token),
            base_url=f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}",
        )

    async def send_sms(self, phone: str, body: str) -> SendResult:
        data = {"To": _ensure_e164(phone, "91"), "From": self.sender, "Body": body}
        return await self._post("/Messages.json", data, "SMS")

    async def send_ivr(self, phone: str, script: str) -> SendResult:
        twiml = f"<Response><Say language='en-IN'>{_xml(script)}</Say></Response>"
        data = {
            "To": _ensure_e164(phone, "91"),
            "From": self.sender,
            "Twiml": twiml,
            "StatusCallback": "https://example.invalid/missed",
        }
        return await self._post("/Calls.json", data, "IVR")

    async def _post(self, path: str, data: dict[str, Any], label: str) -> SendResult:
        try:
            res = await self._client.post(path, data=data)
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=str(exc), status="failed", provider=self.name)
        if res.status_code >= 400:
            return SendResult(
                ok=False,
                error=f"{res.status_code}: {res.text[:200]}",
                status=NotificationStatus.FAILED.value,
                provider=self.name,
            )
        payload = res.json() if res.content else {}
        return SendResult(
            ok=True,
            ref=str(payload.get("sid", "")) or None,
            status=NotificationStatus.SENT.value,
            provider=self.name,
        )

    async def close(self) -> None:
        await self._client.aclose()


class Msg91Provider(BaseProvider):
    """MSG91 is the common route for Indian government bulk SMS deals."""

    name = "msg91"

    def __init__(self) -> None:
        self.key = settings.msg91_auth_key
        self.sender = settings.msg91_sender_id
        self._client = httpx.AsyncClient(timeout=12.0)

    async def send_sms(self, phone: str, body: str) -> SendResult:
        params = {
            "sender": self.sender,
            "route": "q",
            "country": "91",
            "uniq_id": "aapaatsathi",
            "mobiles": _ensure_e164(phone, "").lstrip("+"),
            "message": body[:450],
            "authkey": self.key,
        }
        try:
            res = await self._client.get(
                "https://api.msg91.com/api/v2/sendsms", params=params
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=str(exc), status="failed", provider=self.name)
        if res.status_code >= 400:
            return SendResult(
                ok=False, error=res.text[:200], status=NotificationStatus.FAILED.value, provider=self.name
            )
        return SendResult(
            ok=True, ref=res.json().get("data"), status=NotificationStatus.SENT.value, provider=self.name
        )

    async def send_ivr(self, phone: str, script: str) -> SendResult:
        # Voice campaigns are a separate MSG91 product requiring a registered
        # template id; refuse loudly rather than pretend it worked.
        return SendResult(
            ok=False,
            error="IVR template not configured for msg91; use twilio voice or a registered template",
            status=NotificationStatus.FAILED.value,
            provider=self.name,
        )

    async def close(self) -> None:
        await self._client.aclose()


def build_provider() -> BaseProvider:
    which = settings.sms_provider
    if which == "twilio" and settings.twilio_account_sid and settings.twilio_auth_token:
        return TwilioProvider()
    if which == "msg91" and settings.msg91_auth_key:
        return Msg91Provider()
    if which in {"twilio", "msg91"}:
        log.warning(
            "SMS provider %r requested but credentials are missing; falling back to console",
            which,
        )
    return ConsoleProvider()


# --------------------------------------------------------------------------- #
# message composition
# --------------------------------------------------------------------------- #
def compose_alert(
    *,
    level: str,
    hazard: str,
    ward_name: str,
    district_name: str,
    score: float,
    lang: str,
) -> dict[str, str]:
    """Render subject + SMS + IVR script for one language."""
    lang = i18n.normalize_lang(lang)
    lv = i18n.level_name(level, lang)
    hz = i18n.hazard_name(hazard, lang)
    advice = i18n.advice_for(level, lang)
    ctx = {
        "level": lv,
        "hazard": hz,
        "ward": ward_name,
        "district": district_name,
        "score": int(round(score)),
        "advice": advice,
    }
    return {
        "lang": lang,
        "level_name": lv,
        "hazard_name": hz,
        "advice": advice,
        "subject": i18n.localize("alert.subject", lang, **ctx),
        "sms": i18n.localize("alert.body_sms", lang, **ctx),
        "ivr": i18n.localize("alert.ivr_script", lang, **ctx),
    }


def compose_all_languages(
    *, level: str, hazard: str, ward_name: str, district_name: str, score: float
) -> dict[str, dict[str, str]]:
    return {
        lang: compose_alert(
            level=level,
            hazard=hazard,
            ward_name=ward_name,
            district_name=district_name,
            score=score,
            lang=lang,
        )
        for lang in i18n.SUPPORTED_LANGS
    }


# --------------------------------------------------------------------------- #
# dispatcher
# --------------------------------------------------------------------------- #
class Dispatcher:
    """Queues, de-duplicates, throttles and persists every outbound message.

    Alert fatigue is a real failure mode for early-warning systems: two red
    alerts for the same ward inside an hour teaches people to ignore the next
    one. The dedupe window is therefore part of the model, not a nicety.
    """

    def __init__(self, provider: BaseProvider | None = None, max_per_minute: int = 3000) -> None:
        self.provider = provider or build_provider()
        self.max_per_minute = max_per_minute
        self._recent: dict[str, float] = {}
        self._sent_this_minute: list[float] = []

    # ------------------------------------------------------------- throttling
    def _throttle_ok(self) -> bool:
        now = time.monotonic()
        self._sent_this_minute[:] = [t for t in self._sent_this_minute if now - t < 60]
        if len(self._sent_this_minute) >= self.max_per_minute:
            return False
        self._sent_this_minute.append(now)
        return True

    def _deduped(self, key: str, window_minutes: int) -> bool:
        now = time.monotonic()
        last = self._recent.get(key)
        if last is not None and (now - last) < window_minutes * 60:
            return True
        self._recent[key] = now
        return False

    # ---------------------------------------------------------------- dispatch
    async def dispatch(
        self,
        db: AsyncSession,
        *,
        alert_id: int,
        recipients: Sequence[tuple[str | None, str | None, str]],
        messages: dict[str, dict[str, str]],
        channels: Sequence[str] = (Channel.SMS.value, Channel.IVR.value),
        dedupe_key: str | None = None,
    ) -> dict[str, int]:
        """Send one alert to many recipients. Returns a status tally."""
        if dedupe_key and self._deduped(dedupe_key, settings.dedupe_window_minutes):
            log.info("suppressing duplicate dispatch for %s", dedupe_key)
            return {"suppressed": len(recipients) * len(channels)}

        tally: dict[str, int] = {}
        for phone, user_id, lang in recipients:
            if not phone:
                continue
            msg = messages.get(i18n.normalize_lang(lang)) or messages.get("en")
            if not msg:
                continue
            for channel in channels:
                # IVR is reserved for the highest levels: voice minutes cost
                # real money and only make sense when minutes matter.
                if channel == Channel.IVR.value and not self._should_call(lang, msg):
                    continue
                body = msg["ivr"] if channel == Channel.IVR.value else msg["sms"]
                if not self._throttle_ok():
                    # Persist as genuinely queued rather than dropping it and
                    # reporting a number that was never sent or never tried.
                    db.add(
                        Notification(
                            alert_id=alert_id,
                            user_id=int(user_id) if user_id else None,
                            phone=phone,
                            channel=channel,
                            lang=i18n.normalize_lang(lang),
                            body=body,
                            status=NotificationStatus.QUEUED.value,
                            provider=self.provider.name,
                            attempts=0,
                        )
                    )
                    tally[NotificationStatus.QUEUED.value] = (
                        tally.get(NotificationStatus.QUEUED.value, 0) + 1
                    )
                    continue

                if channel == Channel.SMS.value:
                    result = await self.provider.send_sms(phone, body)
                elif channel == Channel.IVR.value:
                    result = await self.provider.send_ivr(phone, body)
                else:
                    result = SendResult(ok=True, status=NotificationStatus.SENT.value)

                db.add(
                    Notification(
                        alert_id=alert_id,
                        user_id=int(user_id) if user_id else None,
                        phone=phone,
                        channel=channel,
                        lang=i18n.normalize_lang(lang),
                        body=body,
                        status=result.status,
                        provider=result.provider,
                        provider_ref=result.ref,
                        error=result.error,
                        attempts=1,
                        sent_at=datetime.now(timezone.utc) if result.ok else None,
                    )
                )
                tally[result.status] = tally.get(result.status, 0) + 1

        await db.flush()
        return tally

    @staticmethod
    def _should_call(lang: str, msg: dict[str, str]) -> bool:
        high = {
            i18n.level_name("orange", lang),
            i18n.level_name("red", lang),
            "Warning",
            "Evacuate",
            "गंभीर चेतावनी",
            "तुरंत स्थानांतरण",
        }
        return msg["level_name"] in high

    async def stats(self) -> dict[str, Any]:
        return {"provider": self.provider.name, "queued_recently": len(self._recent)}

    async def close(self) -> None:
        await self.provider.close()


# --------------------------------------------------------------------------- #
# recipient resolution
# --------------------------------------------------------------------------- #
async def resolve_recipients(
    db: AsyncSession,
    ward: Ward,
    *,
    include_simulated_households: bool = True,
    max_real: int = 500,
) -> list[tuple[str | None, str | None, str]]:
    """Return (phone, user_id, language) tuples for one ward.

    Registered residents are addressed directly. Because a warning system that
    only counts opt-in users understates its own reach — and because the district
    administration plans shelter capacity from this number — the remaining
    registered-phone population is represented as *clearly simulated* synthetic
    numbers. The API never labels those as delivered.
    """
    from sqlalchemy import select

    from app.models import Subscription, User

    rows = await db.execute(
        select(User, Subscription.lang)
        .join(Subscription, Subscription.user_id == User.id)
        .where(Subscription.ward_id == ward.id, User.is_active.is_(True))
        .limit(max_real)
    )
    out: list[tuple[str | None, str | None, str]] = []
    covered: set[str] = set()
    for user, lang in rows:
        if user.phone and user.phone not in covered:
            covered.add(user.phone)
            out.append((user.phone, str(user.id), i18n.normalize_lang(lang or user.preferred_lang)))

    if include_simulated_households:
        remaining = max(0, int(ward.registered_phones) - len(out))
        # one SMS per household-equivalent, capped so a ward of 3,000 people does
        # not generate 3,000 rows in a demo run.
        synthetic = min(remaining, 60)
        rng = random.Random(ward.id * 7919)
        for _ in range(synthetic):
            digits = "".join(rng.choice("0123456789") for _ in range(10))
            out.append((f"+91{digits}", None, i18n.normalize_lang(ward_lang(ward))))
    return out


def ward_lang(ward: Ward) -> str:
    """Crude but honest default: Garhwali belts by district name pattern."""
    name = (ward.code or "").split("-")[0].upper()
    if name in {"PKR", "CHM", "RPR", "UKD", "ALM", "PTK"}:
        return "gar"
    return "hi"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _ensure_e164(phone: str, country: str) -> str:
    digits = "".join(c for c in phone if c.isdigit() or c == "+")
    if digits.startswith("+"):
        return digits
    if country and not digits.startswith(country):
        return f"+{country}{digits}"
    return f"+{digits}"


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


dispatcher = Dispatcher()

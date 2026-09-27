"""Delivery accounting, analytics, audit trail, subscriptions and health."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.config import settings
from app.core.deps import AdminOnly, CurrentUser, DbSession, resolve_ward
from app.models import (
    Alert,
    AuditLog,
    Channel,
    District,
    Notification,
    NotificationStatus,
    Subscription,
    User,
    Ward,
)
from app.schemas import AuditOut, NotificationOut
from app.services import assembly, i18n, notifier, risk_engine

router = APIRouter(tags=["operations"])


# --------------------------------------------------------------------------- #
# delivery accounting
# --------------------------------------------------------------------------- #
@router.get("/notifications")
async def list_notifications(
    db: DbSession,
    admin: AdminOnly,
    status: str | None = None,
    channel: str | None = None,
    alert_code: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    stmt = select(Notification).order_by(Notification.created_at.desc())
    if status:
        stmt = stmt.where(Notification.status == status)
    if channel:
        stmt = stmt.where(Notification.channel == channel)
    if alert_code:
        rows = await db.execute(select(Alert).where(Alert.code == alert_code))
        alert = rows.scalars().first()
        if not alert:
            raise HTTPException(404, f"No alert '{alert_code}'")
        stmt = stmt.where(Notification.alert_id == alert.id)
    rows = await db.execute(stmt.limit(min(limit, 500)))
    items = list(rows.scalars().all())
    return {
        "count": len(items),
        # Phones are masked in the list view: a breach of this table should not
        # hand over a resident directory.
        "notifications": [
            {
                **NotificationOut.model_validate(n).model_dump(),
                "phone": _mask(n.phone),
            }
            for n in items
        ],
    }


def _mask(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    return f"+{digits[:2]}••••{digits[-4:]}" if len(digits) >= 6 else "••••"


@router.get("/notifications/stats")
async def notification_stats(db: DbSession, admin: AdminOnly) -> dict[str, Any]:
    by_status = dict(
        (
            await db.execute(
                select(Notification.status, func.count(Notification.id)).group_by(
                    Notification.status
                )
            )
        ).all()
    )
    by_channel = dict(
        (
            await db.execute(
                select(Notification.channel, func.count(Notification.id)).group_by(
                    Notification.channel
                )
            )
        ).all()
    )
    by_lang = dict(
        (
            await db.execute(
                select(Notification.lang, func.count(Notification.id)).group_by(Notification.lang)
            )
        ).all()
    )
    total = sum(by_status.values())
    reach = (
        await db.execute(
            select(func.coalesce(func.sum(Alert.reach_target), 0)).where(Alert.reach_target > 0)
        )
    ).scalar()
    simulated = by_status.get(NotificationStatus.SIMULATED.value, 0)
    return {
        "provider": notifier.dispatcher.provider.name,
        "simulated": notifier.dispatcher.provider.name == "console",
        "by_status": {k: int(v) for k, v in by_status.items()},
        "by_channel": {k: int(v) for k, v in by_channel.items()},
        "by_lang": {k: int(v) for k, v in by_lang.items()},
        "total": int(total),
        "reach_target": int(reach or 0),
        "note": (
            f"{simulated} message(s) were SIMULATED: the console provider records what "
            "would have been sent without touching a network. Set SMS_PROVIDER=twilio "
            "(or msg91) with credentials for real delivery."
            if simulated
            else "All recorded messages were accepted by a live provider."
        ),
    }


@router.post("/notifications/test")
async def test_notification(db: DbSession, admin: AdminOnly, to_phone: str | None = None) -> dict[str, Any]:
    """Send one test message to the caller's own number. Never a crowd."""
    phone = to_phone or admin.phone
    if not phone:
        raise HTTPException(422, "No phone on your account; pass ?to_phone=")
    messages = notifier.compose_all_languages(
        level="yellow",
        hazard="landslide",
        ward_name="Test ward",
        district_name="Test district",
        score=51,
    )
    result = await notifier.dispatcher.provider.send_sms(phone, messages["en"]["sms"])
    record = Notification(
        user_id=admin.id,
        phone=phone,
        channel=Channel.SMS.value,
        lang="en",
        body=messages[admin.preferred_lang]["sms"] if admin.preferred_lang in messages else messages["en"]["sms"],
        status=result.status,
        provider=result.provider,
        provider_ref=result.ref,
        error=result.error,
        attempts=1,
        sent_at=datetime.now(timezone.utc) if result.ok else None,
    )
    db.add(record)
    await db.flush()
    return {
        "ok": result.ok,
        "status": result.status,
        "provider": result.provider,
        "error": result.error,
        "body_preview": record.body,
    }


# --------------------------------------------------------------------------- #
# analytics
# --------------------------------------------------------------------------- #
@router.get("/analytics/summary")
async def summary(db: DbSession) -> dict[str, Any]:
    return await assembly.analytics(db)


@router.get("/analytics/timeseries")
async def timeseries(db: DbSession, hours: int = Query(default=24, ge=1, le=168)) -> dict[str, Any]:
    return {"hours": hours, "points": await assembly.timeseries(db, hours=hours)}


@router.get("/analytics/audit")
async def audit_trail(
    db: DbSession,
    admin: AdminOnly,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    rows = await db.execute(stmt)
    return {"entries": [AuditOut.model_validate(a).model_dump() for a in rows.scalars()]}


@router.get("/analytics/coverage")
async def coverage(db: DbSession) -> dict[str, Any]:
    """Per-district rollout view: wards mapped, population reached, alerts out."""
    wards = await assembly.all_wards(db)
    scores = await assembly.live_scores(db, wards)
    districts: dict[str, dict[str, Any]] = {}
    for ward in wards:
        name = ward.district.name if ward.district else "Unknown"
        entry = districts.setdefault(
            name,
            {
                "district": name,
                "wards": 0,
                "population": 0,
                "phones": 0,
                "exposed": 0,
                "mean_score": 0.0,
                "worst_level": "green",
                "_sum": 0.0,
            },
        )
        score = scores[ward.id]
        entry["wards"] += 1
        entry["population"] += ward.population
        entry["phones"] += ward.registered_phones
        entry["exposed"] += score.population_at_risk
        entry["_sum"] += score.score
        order = risk_engine.LEVEL_ORDER
        if order.index(score.level) > order.index(entry["worst_level"]):
            entry["worst_level"] = score.level
    out = []
    for entry in districts.values():
        entry["mean_score"] = round(entry.pop("_sum") / max(1, entry["wards"]), 2)
        out.append(entry)
    out.sort(key=lambda e: e["exposed"], reverse=True)
    return {"districts": out, "users_reachable": await assembly.reachable_users(db)}


# --------------------------------------------------------------------------- #
# subscriptions
# --------------------------------------------------------------------------- #
@router.get("/me/subscriptions")
async def my_subscriptions(db: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.ward_id)
    )
    subs = list(rows.scalars().all())
    ward_ids = {s.ward_id for s in subs}
    wards: dict[int, Ward] = {}
    if ward_ids:
        wrows = await db.execute(select(Ward).where(Ward.id.in_(list(ward_ids))))
        wards = {w.id: w for w in wrows.scalars()}
    return [
        {
            "id": sub.id,
            "ward_id": sub.ward_id,
            "ward_code": wards[sub.ward_id].code if sub.ward_id in wards else None,
            "ward_name": wards[sub.ward_id].name if sub.ward_id in wards else None,
            "channel": sub.channel,
            "lang": sub.lang,
            "min_level": sub.min_level,
        }
        for sub in subs
    ]


@router.post("/me/subscriptions/{ward_code}")
async def subscribe(
    ward_code: str,
    db: DbSession,
    user: CurrentUser,
    channel: str = Query(default="sms", description="sms | ivr | push | inapp"),
    lang: str = Query(default="en", description="en | hi | gar"),
    min_level: str = Query(default="yellow", description="blue | yellow | orange | red"),
) -> dict[str, Any]:
    """Opt in to warnings for a ward — usually home, sometimes a relative's."""
    ward = await resolve_ward(db, ward_code)
    if channel not in {c.value for c in Channel}:
        raise HTTPException(422, f"Unknown channel '{channel}'")
    rows = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id, Subscription.ward_id == ward.id
        )
    )
    sub = rows.scalars().first()
    if sub is None:
        sub = Subscription(
            user_id=user.id,
            ward_id=ward.id,
            channel=channel,
            lang=lang,
            min_level=min_level,
        )
        db.add(sub)
    else:
        sub.channel = channel
        sub.lang = lang
        sub.min_level = min_level
    user.ward_id = ward.id
    user.district_id = ward.district_id
    user.preferred_lang = lang
    await db.flush()
    return {
        "ward": ward.code,
        "ward_name": ward.name,
        "channel": sub.channel,
        "lang": sub.lang,
        "min_level": sub.min_level,
        "message": f"You will get {sub.min_level}+ warnings for {ward.name} by {sub.channel}.",
    }


@router.delete("/me/subscriptions/{ward_code}", status_code=200)
async def unsubscribe(ward_code: str, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    ward = await resolve_ward(db, ward_code)
    rows = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id, Subscription.ward_id == ward.id
        )
    )
    sub = rows.scalars().first()
    if sub is None:
        raise HTTPException(404, "No such subscription")
    await db.delete(sub)
    await db.flush()
    return {"ward": ward.code, "message": "Unsubscribed"}


# --------------------------------------------------------------------------- #
# health & metadata
# --------------------------------------------------------------------------- #
@router.get("/health")
async def health(db: DbSession) -> dict[str, Any]:
    ward_count = (await db.execute(select(func.count(District.id)))).scalar() or 0
    return {
        "status": "ok",
        "version": settings.version,
        "environment": settings.environment,
        "database": "sqlite" if settings.is_sqlite else "postgres",
        "notifications": notifier.dispatcher.provider.name,
        "simulated_delivery": notifier.dispatcher.provider.name == "console",
        "seed_present": ward_count > 0,
        "time": datetime.now(timezone.utc),
    }


@router.get("/meta")
async def meta(db: DbSession) -> dict[str, Any]:
    """Everything the frontend needs to render labels without hard-coding them."""
    ward_count = int(
        (await db.execute(select(func.count(Ward.id)))).scalar() or 0
    )
    return {
        "app": {
            "name": settings.app_name,
            "title": "AapaatSathi",
            "title_hi": "आपतसाथी",
            "tagline": settings.app_tagline,
            "version": settings.version,
        },
        "levels": risk_engine.LEVEL_ORDER,
        "level_names": {
            level: {lang: i18n.level_name(level, lang) for lang in i18n.SUPPORTED_LANGS}
            for level in risk_engine.LEVEL_ORDER
        },
        "hazards": list(i18n.HAZARD_NAMES.keys()),
        "hazard_names": {
            hz: {lang: i18n.hazard_name(hz, lang) for lang in i18n.SUPPORTED_LANGS}
            for hz in i18n.HAZARD_NAMES
        },
        "channels": [c.value for c in Channel],
        "report_statuses": ["new", "under_review", "confirmed", "dismissed", "resolved"],
        "road_statuses": ["open", "caution", "partial", "closed"],
        "languages": list(i18n.SUPPORTED_LANGS),
        "catalog": i18n.catalog("en"),
        "emergency_numbers": {"control_room": "1070", "national": "112", "police": "100", "ambulance": "108"},
        "model_version": risk_engine.MODEL_VERSION,
        "telemetry": "simulated" if not settings.use_live_weather else "open-meteo",
        "ward_count": ward_count,
    }

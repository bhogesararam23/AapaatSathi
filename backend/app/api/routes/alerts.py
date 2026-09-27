"""Alert endpoints: browse, acknowledge, author, broadcast, revoke."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.core.deps import AdminOnly, CurrentUser, DbSession, MaybeUser, resolve_district, resolve_ward
from app.models import Alert, AlertStatus, District, Role, Ward
from app.schemas import AlertCreateIn, AlertOut, AlertStatusIn
from app.services import alerts as svc
from app.services import notifier
from app.services.risk_engine import WardScore

router = APIRouter(prefix="/alerts", tags=["alerts"])


async def _get(db, code: str) -> Alert:
    rows = await db.execute(select(Alert).where(Alert.code == code))
    alert = rows.scalars().first()
    if not alert:
        raise HTTPException(404, f"No alert '{code}'")
    return alert


def _guard_district(user, alert: Alert) -> None:
    """A district admin may not touch another district's warnings."""
    if user.role == Role.SYSTEM_ADMIN.value:
        return
    if user.district_id and alert.district_id and alert.district_id != user.district_id:
        raise HTTPException(403, "That alert belongs to another district")


@router.get("")
async def list_alerts(
    db: DbSession,
    user: MaybeUser,
    active_only: bool = Query(default=False),
    level: str | None = Query(default=None),
    ward: str | None = Query(default=None),
    district: str | None = Query(default=None),
    since_hours: int = Query(default=72, ge=1, le=24 * 30),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    stmt = select(Alert).where(Alert.issued_at >= cutoff).order_by(Alert.issued_at.desc())
    if active_only:
        stmt = stmt.where(Alert.status == AlertStatus.ACTIVE.value)
    if level:
        stmt = stmt.where(Alert.level == level)
    if ward:
        target = await resolve_ward(db, ward)
        stmt = stmt.where(Alert.ward_id == target.id)
    district_id = None
    if district:
        target_d = await resolve_district(db, district)
        district_id = target_d.id
        stmt = stmt.where(Alert.district_id == district_id)
    if user and user.role == Role.DISTRICT_ADMIN.value and user.district_id and not district_id:
        stmt = stmt.where(Alert.district_id == user.district_id)

    rows = await db.execute(stmt.limit(min(limit, 500)))
    items = list(rows.scalars().all())
    return {
        "count": len(items),
        "alerts": [AlertOut.model_validate(a).model_dump() for a in items],
        "delivery_mode": notifier.dispatcher.provider.name,
    }


@router.get("/live")
async def live_alerts(db: DbSession, user: MaybeUser) -> dict[str, Any]:
    """Un-expired alerts, worst first — what the citizen banner shows."""
    now = datetime.now(timezone.utc)
    rows = await db.execute(
        select(Alert)
        .where(Alert.status == AlertStatus.ACTIVE.value)
        .order_by(Alert.issued_at.desc())
        .limit(200)
    )
    out = []
    for alert in rows.scalars():
        expires = alert.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires and expires < now:
            continue
        if user and user.role == Role.DISTRICT_ADMIN.value and alert.district_id != user.district_id:
            continue
        payload = AlertOut.model_validate(alert).model_dump()
        ward = await db.get(Ward, alert.ward_id) if alert.ward_id else None
        payload["ward_name"] = ward.name if ward else None
        payload["minutes_left"] = (
            max(0, int((expires - now).total_seconds() // 60)) if expires else None
        )
        out.append(payload)
    order = {"red": 0, "orange": 1, "yellow": 2, "blue": 3, "green": 4}
    out.sort(key=lambda a: (order.get(a["level"], 9), a["issued_at"]), reverse=False)
    return {"count": len(out), "alerts": out}


@router.get("/{code}", response_model=AlertOut)
async def get_alert(code: str, db: DbSession) -> AlertOut:
    return AlertOut.model_validate(await _get(db, code))


@router.post("", response_model=AlertOut, status_code=201)
async def create_alert(body: AlertCreateIn, db: DbSession, admin: AdminOnly) -> AlertOut:
    """Author (and optionally broadcast) a warning by hand.

    Manual broadcasts are recorded with ``auto_issued=false`` and an actor, so
    the audit trail always shows who put a district-level warning out.
    """
    ward: Ward | None = await resolve_ward(db, body.ward_code) if body.ward_code else None
    district: District | None = None
    if not ward and body.district_code:
        district = await resolve_district(db, body.district_code)
    if ward and admin.role == Role.DISTRICT_ADMIN.value and ward.district_id != admin.district_id:
        raise HTTPException(403, "That ward is outside your district")

    alert = await svc.create_alert(
        db,
        ward=ward,
        district=district,
        score=None,
        hazard=body.hazard_type,
        level=body.level,
        title=body.title,
        message=body.message,
        issued_by_id=admin.id,
        auto_issued=False,
        channels=body.channels,
        ttl_minutes=body.ttl_minutes,
    )
    reach: dict[str, int] = {}
    if body.broadcast:
        reach = await svc.broadcast_alert(db, alert)
    await svc.audit(
        db,
        actor_id=admin.id,
        actor_label=admin.full_name,
        action="alert.manual_broadcast" if body.broadcast else "alert.manual_draft",
        entity="alert",
        entity_id=alert.code,
        detail={"level": body.level, "ward": body.ward_code, "district": body.district_code, "reach": reach},
    )
    await db.commit()
    return AlertOut.model_validate(alert).model_copy(update={"reach": reach})


@router.post("/{code}/broadcast")
async def rebroadcast(code: str, db: DbSession, admin: AdminOnly) -> dict[str, Any]:
    alert = await _get(db, code)
    _guard_district(admin, alert)
    tally = await svc.broadcast_alert(db, alert)
    await svc.audit(
        db,
        actor_id=admin.id,
        actor_label=admin.full_name,
        action="alert.rebroadcast",
        entity="alert",
        entity_id=code,
        detail={"reach": tally},
    )
    await db.commit()
    return {"alert": code, "reach": tally, "delivered": alert.delivered}


@router.post("/{code}/acknowledge")
async def acknowledge(code: str, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Citizen/responder ack — the metric that tells an SDM if warnings landed."""
    alert = await _get(db, code)
    alert.acknowledged = (alert.acknowledged or 0) + 1
    if user.role != Role.CITIZEN.value:
        alert.status = AlertStatus.ACKNOWLEDGED.value
    await db.flush()
    return {"alert": code, "acknowledged": alert.acknowledged}


@router.patch("/{code}/status", response_model=AlertOut)
async def set_status(code: str, body: AlertStatusIn, db: DbSession, admin: AdminOnly) -> AlertOut:
    alert = await _get(db, code)
    _guard_district(admin, alert)
    alert.status = body.status
    await svc.audit(
        db,
        actor_id=admin.id,
        actor_label=admin.full_name,
        action="alert.status",
        entity="alert",
        entity_id=code,
        detail={"status": body.status},
    )
    await db.commit()
    return AlertOut.model_validate(alert)


@router.post("/preview")
async def preview(body: AlertCreateIn, db: DbSession, admin: AdminOnly) -> dict[str, Any]:
    """Render exactly what every language group will receive — before sending it.

    A mistranslated evacuation order is a worse outcome than no order, so the
    console makes proofreading all three variants a step, not an afterthought.
    """
    ward: Ward | None = await resolve_ward(db, body.ward_code) if body.ward_code else None
    district: District | None = None
    if not ward and body.district_code:
        district = await resolve_district(db, body.district_code)
    ward_name = ward.name if ward else (district.name if district else "the district")
    district_name = (
        ward.district.name
        if ward and ward.district
        else district.name if district
        else "Uttarakhand"
    )
    from app.services.risk_engine import DEFAULT_THRESHOLDS

    messages = notifier.compose_all_languages(
        level=body.level,
        hazard=body.hazard_type,
        ward_name=ward_name,
        district_name=district_name,
        score=DEFAULT_THRESHOLDS.get(body.level, 0) + 1,
    )
    recipients = (
        await notifier.resolve_recipients(db, ward, include_simulated_households=False)
        if ward
        else []
    )
    return {
        "messages": messages,
        "real_recipients": len(recipients),
        "estimated_reach": (ward.registered_phones if ward else int((district.population if district else 0) * 0.55)),
        "channels": body.channels,
    }

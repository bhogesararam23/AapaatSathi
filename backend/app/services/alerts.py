"""Alert lifecycle: detect escalation, compose, broadcast, account for reach.

A score is not a warning. The operational value is in the *transition* — the
moment a ward crosses from advisory into evacuation territory — so this module
compares each run against the previous persisted state and only escalates on
real movement. That single rule is what keeps the system from shouting constantly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import OPS, PUBLIC, manager
from app.models import (
    Alert,
    AlertStatus,
    AuditLog,
    Channel,
    District,
    NotificationStatus,
    RiskLevel,
    RiskModelConfig,
    Ward,
    WardRisk,
)
from app.services import i18n, notifier
from app.services.risk_engine import LEVEL_ORDER, WardScore, evaluate_wards

log = logging.getLogger("aapaatsathi.alerts")


@dataclass
class EscalationReport:
    evaluated: int = 0
    created: int = 0
    suppressed: int = 0
    escalated: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.escalated is None:
            self.escalated = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "created": self.created,
            "suppressed": self.suppressed,
            "escalated": self.escalated,
        }


async def active_alert(db: AsyncSession, ward_id: int, level: str) -> Alert | None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=notifier.settings.dedupe_window_minutes)
    rows = await db.execute(
        select(Alert).where(
            Alert.ward_id == ward_id,
            Alert.level == level,
            Alert.status == AlertStatus.ACTIVE.value,
            Alert.issued_at >= cutoff,
        )
    )
    return rows.scalars().first()


async def previous_levels(db: AsyncSession, ward_ids: Sequence[int], before: datetime) -> dict[int, str]:
    """Snapshot each ward's most recent level *before* this run.

    Must be read before the new scores are persisted: comparing a fresh row
    against itself makes every escalation look like a no-op, and the system
    would silently stop warning people.
    """
    if not ward_ids:
        return {}
    rows = await db.execute(
        select(WardRisk.ward_id, WardRisk.level, WardRisk.computed_at)
        .where(WardRisk.ward_id.in_(list(ward_ids)), WardRisk.computed_at < before)
        .order_by(WardRisk.computed_at.desc())
    )
    out: dict[int, str] = {}
    for ward_id, level, _at in rows:
        out.setdefault(int(ward_id), level)
    return out


async def active_model(db: AsyncSession) -> RiskModelConfig | None:
    rows = await db.execute(
        select(RiskModelConfig).where(RiskModelConfig.is_active.is_(True)).limit(1)
    )
    return rows.scalars().first()


async def audit(
    db: AsyncSession,
    *,
    actor_id: int | None,
    actor_label: str,
    action: str,
    entity: str,
    entity_id: Any = "",
    detail: dict[str, Any] | None = None,
    ip: str = "",
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            actor_label=actor_label,
            action=action,
            entity=entity,
            entity_id=str(entity_id),
            detail=detail or {},
            ip=ip,
        )
    )
    await db.flush()


# --------------------------------------------------------------------------- #
# the sweep
# --------------------------------------------------------------------------- #
async def run_sweep(
    db: AsyncSession,
    wards: Sequence[Ward],
    *,
    auto_broadcast: bool = True,
    actor_label: str = "scheduler",
) -> EscalationReport:
    """Recompute risk for `wards`, persist it, and escalate where warranted."""
    model = await active_model(db)
    weights = model.weights if model else None
    thresholds = model.thresholds if model else None

    now = datetime.now(timezone.utc)
    # Read the prior state first — see previous_levels().
    prior = await previous_levels(db, [w.id for w in wards], now)
    results = await evaluate_wards(db, wards, weights=weights, thresholds=thresholds)
    report = EscalationReport(evaluated=len(results))

    for ward, score in results:
        payload = ward_payload(ward, score)
        await manager.publish("risk:update", payload, channel=PUBLIC)

        if score.level not in {RiskLevel.YELLOW.value, RiskLevel.ORANGE.value, RiskLevel.RED.value}:
            continue
        prev = prior.get(ward.id, RiskLevel.GREEN.value)
        if LEVEL_ORDER.index(score.level) <= LEVEL_ORDER.index(prev):
            continue  # not an escalation: same level or a downgrade
        if not auto_broadcast:
            report.suppressed += 1
            continue
        if await active_alert(db, ward.id, score.level):
            report.suppressed += 1
            continue

        alert = await create_alert(
            db,
            ward=ward,
            district=ward.district,
            score=score,
            hazard=_dominant_hazard(ward, score),
            level=score.level,
            issued_by_id=None,
            auto_issued=True,
            channels=[Channel.SMS.value, Channel.IVR.value],
        )
        dispatch = await broadcast_alert(db, alert)
        report.created += 1
        report.escalated.append(
            {
                "alert_code": alert.code,
                "ward": ward.code,
                "ward_name": ward.name,
                "district": ward.district.name if ward.district else "",
                "from": prev,
                "to": score.level,
                "score": score.score,
                "population_at_risk": score.population_at_risk,
                "reach": dispatch,
            }
        )
        await audit(
            db,
            actor_id=None,
            actor_label=actor_label,
            action="alert.auto_issued",
            entity="alert",
            entity_id=alert.code,
            detail={"from": prev, "to": score.level, "score": score.score},
        )
    return report


def _dominant_hazard(ward: Ward, score: WardScore) -> str:
    """Pick the label a resident should see, from the biggest contributor."""
    if not score.factors:
        return "landslide"
    top = max(score.factors, key=lambda f: f.contribution)
    if top.key in {"rain_intensity", "forecast_6h"} and ward.river_distance_km < 1.2:
        return "flash_flood"
    if top.key == "drainage":
        return "flash_flood"
    if top.key == "glacial_lake":
        return "glacial_lake"
    return "landslide"


# --------------------------------------------------------------------------- #
# authoring & broadcasting
# --------------------------------------------------------------------------- #
async def create_alert(
    db: AsyncSession,
    *,
    ward: Ward | None,
    district: District | None = None,
    score: WardScore | None = None,
    hazard: str = "landslide",
    level: str = RiskLevel.YELLOW.value,
    title: str | None = None,
    message: str | None = None,
    issued_by_id: int | None = None,
    auto_issued: bool = False,
    channels: Sequence[str] = (Channel.SMS.value, Channel.IVR.value),
    ttl_minutes: int = 240,
) -> Alert:
    ward_name = ward.name if ward else (district.name if district else "the district")
    district_name = (
        (ward.district.name if ward and ward.district else district.name if district else "Uttarakhand")
    )
    value = score.score if score else _level_floor(level)

    localized = notifier.compose_all_languages(
        level=level,
        hazard=hazard,
        ward_name=ward_name,
        district_name=district_name,
        score=value,
    )
    alert = Alert(
        code=_code(hazard),
        ward_id=ward.id if ward else None,
        district_id=(ward.district_id if ward else district.id if district else None),
        hazard_type=hazard,
        level=level,
        title=title or localized["en"]["subject"],
        message=message or localized["en"]["sms"],
        localized=localized,
        score=value,
        advice=localized["en"]["advice"],
        auto_issued=auto_issued,
        issued_by_id=issued_by_id,
        status=AlertStatus.ACTIVE.value,
        channels=list(channels),
        reach_target=(ward.registered_phones if ward else 0) or _district_phones(district),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )
    db.add(alert)
    await db.flush()
    return alert


def _district_phones(district: District | None) -> int:
    return int((district.population if district else 0) * 0.55)


def _level_floor(level: str) -> float:
    from app.services.risk_engine import DEFAULT_THRESHOLDS

    return float(DEFAULT_THRESHOLDS.get(level, 0))


def _code(hazard: str) -> str:
    from app.core.security import generate_code

    return generate_code(f"AL-{hazard[:3].upper()}")


async def broadcast_alert(
    db: AsyncSession, alert: Alert, *, channels: Sequence[str] | None = None
) -> dict[str, int]:
    """Deliver an alert to its ward (or whole district) and account for reach."""
    use_channels = list(channels or alert.channels or [Channel.SMS.value])
    messages = alert.localized or {}
    tally: dict[str, int] = {}

    wards: list[Ward] = []
    if alert.ward_id:
        rows = await db.execute(select(Ward).where(Ward.id == alert.ward_id))
        if (ward := rows.scalars().first()):
            wards = [ward]
    elif alert.district_id:
        rows = await db.execute(select(Ward).where(Ward.district_id == alert.district_id))
        wards = list(rows.scalars().all())

    for ward in wards:
        recipients = await notifier.resolve_recipients(db, ward)
        result = await notifier.dispatcher.dispatch(
            db,
            alert_id=alert.id,
            recipients=recipients,
            messages=messages,
            channels=use_channels,
            dedupe_key=f"{alert.ward_id or alert.district_id}:{alert.level}:{alert.hazard_type}",
        )
        for key, value in result.items():
            tally[key] = tally.get(key, 0) + value

    delivered = tally.get(NotificationStatus.SENT.value, 0)
    simulated = tally.get(NotificationStatus.SIMULATED.value, 0)
    alert.delivered = delivered + simulated
    alert.reach_target = alert.reach_target or (delivered + simulated)

    await manager.publish(
        "alert:new",
        {
            "code": alert.code,
            "level": alert.level,
            "title": alert.title,
            "message": alert.message,
            "ward_id": alert.ward_id,
            "ward": wards[0].name if wards else None,
            "district_id": alert.district_id,
            "hazard": alert.hazard_type,
            "score": alert.score,
            "advice": alert.advice,
            "localized": alert.localized,
            "auto_issued": alert.auto_issued,
            "issued_at": alert.issued_at.isoformat() if alert.issued_at else None,
            "reach": tally,
            "delivery_mode": notifier.dispatcher.provider.name,
        },
        channel=PUBLIC,
    )
    await manager.publish("ops:activity", {"action": "broadcast", "alert": alert.code, "reach": tally}, channel=OPS)
    await db.flush()
    return tally


def ward_payload(ward: Ward, score: WardScore) -> dict[str, Any]:
    """Compact public geometry + score, safe for the citizen map."""
    return {
        "ward_id": ward.id,
        "code": ward.code,
        "name": ward.name,
        "name_hi": ward.name_hi,
        "district": ward.district.name if ward.district else None,
        "district_id": ward.district_id,
        "latitude": ward.latitude,
        "longitude": ward.longitude,
        "polygon": ward.polygon or [],
        "score": score.score,
        "level": score.level,
        "confidence": score.confidence,
        "crowd_uplift": score.crowd_uplift,
        "probability_24h": score.probability_24h,
        "population": ward.population,
        "population_at_risk": score.population_at_risk,
        "factors": [f.to_dict() for f in score.factors],
    }


async def risk_snapshot(db: AsyncSession, ward_ids: Sequence[int] | None = None) -> dict[int, WardRisk]:
    """Latest persisted risk row per ward — the read path for the map."""
    stmt = (
        select(WardRisk)
        .order_by(WardRisk.computed_at.desc(), WardRisk.id.desc())
    )
    if ward_ids:
        stmt = stmt.where(WardRisk.ward_id.in_(list(ward_ids)))
    rows = await db.execute(stmt)
    out: dict[int, WardRisk] = {}
    for record in rows.scalars():
        out.setdefault(record.ward_id, record)
    return out


async def counts_by_level(db: AsyncSession) -> dict[str, int]:
    """Ward tally using each ward's most recent risk row."""
    latest = (
        select(
            WardRisk.ward_id.label("ward_id"),
            func.max(WardRisk.computed_at).label("latest_at"),
        )
        .group_by(WardRisk.ward_id)
        .subquery()
    )
    rows = await db.execute(
        select(WardRisk.level, func.count(func.distinct(WardRisk.ward_id)))
        .join(
            latest,
            and_(
                WardRisk.ward_id == latest.c.ward_id,
                WardRisk.computed_at == latest.c.latest_at,
            ),
        )
        .group_by(WardRisk.level)
    )
    base = {level: 0 for level in LEVEL_ORDER}
    for level, count in rows:
        if level in base:
            base[level] = int(count)
    return base

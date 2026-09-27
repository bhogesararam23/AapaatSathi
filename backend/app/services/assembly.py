"""Read-model assembly: turns ORM rows + live engine output into API payloads.

Kept separate from the routers so the same computed view is used by the map,
the dashboard, the WebSocket fan-out and the tests — one definition of "current
risk", no drift between surfaces.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Alert,
    District,
    HazardReport,
    RoadSegment,
    RiskLevel,
    RiskModelConfig,
    Shelter,
    TelemetryReading,
    User,
    Ward,
    WardRisk,
)
from app.services import geo, ingest, risk_engine
from app.services.risk_engine import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    MODEL_VERSION,
    WardScore,
    evaluate_wards,
)

FACTOR_DOCS: dict[str, dict[str, str]] = {
    "rain_intensity": {"name": "Rainfall intensity", "source": "Rain gauge / Open-Meteo nowcast", "kind": "dynamic"},
    "rain_antecedent": {"name": "Antecedent rainfall", "source": "72 h gauge accumulation", "kind": "dynamic"},
    "soil_saturation": {"name": "Soil saturation", "source": "Probe where available, else inferred from 24 h accumulation", "kind": "dynamic"},
    "forecast_6h": {"name": "6 h forecast rainfall", "source": "Numerical weather forecast grid", "kind": "forecast"},
    "slope": {"name": "Slope angle", "source": "SRTM/CartDEM 30 m derived", "kind": "static"},
    "geology": {"name": "Lithology", "source": "GSI National Geomorphoscape / Geological Survey of India", "kind": "static"},
    "structural": {"name": "Thrust-zone proximity", "source": "MBT/MCT fault traces", "kind": "static"},
    "drainage": {"name": "Channel proximity", "source": "Drainage network + gauge stage", "kind": "static"},
    "vegetation_loss": {"name": "Vegetation deficit", "source": "Sentinel-2 NDVI anomaly", "kind": "static"},
    "event_history": {"name": "Past event density", "source": "State disaster records", "kind": "static"},
}


async def all_wards(db: AsyncSession, district_code: str | None = None) -> list[Ward]:
    stmt = select(Ward).order_by(Ward.code)
    if district_code:
        stmt = stmt.join(District, Ward.district_id == District.id).where(
            District.code == district_code.strip().upper()
        )
    return list((await db.execute(stmt)).scalars().all())


async def live_scores(
    db: AsyncSession,
    wards: Sequence[Ward] | None = None,
    *,
    persist: bool = False,
) -> dict[int, WardScore]:
    """Current engine output for every ward (persist=False for read paths)."""
    wards = list(wards) if wards is not None else await all_wards(db)
    model = await active_model(db)
    pairs = await evaluate_wards(
        db,
        wards,
        weights=model.weights if model else None,
        thresholds=model.thresholds if model else None,
        persist=persist,
    )
    if persist:
        await db.commit()
    return {ward.id: score for ward, score in pairs}


async def active_model(db: AsyncSession) -> RiskModelConfig | None:
    rows = await db.execute(
        select(RiskModelConfig).where(RiskModelConfig.is_active.is_(True)).limit(1)
    )
    return rows.scalars().first()


async def latest_risk_rows(db: AsyncSession) -> dict[int, WardRisk]:
    latest = (
        select(WardRisk.ward_id.label("wid"), func.max(WardRisk.id).label("rid"))
        .group_by(WardRisk.ward_id)
        .subquery()
    )
    rows = await db.execute(
        select(WardRisk).join(latest, WardRisk.id == latest.c.rid)
    )
    return {r.ward_id: r for r in rows.scalars()}


# --------------------------------------------------------------------------- #
# payloads
# --------------------------------------------------------------------------- #
def score_dict(ward: Ward, score: WardScore) -> dict[str, Any]:
    return {
        "ward_id": ward.id,
        "code": ward.code,
        "name": ward.name,
        "name_hi": ward.name_hi,
        "district": ward.district.name if ward.district else None,
        "district_id": ward.district_id,
        "latitude": ward.latitude,
        "longitude": ward.longitude,
        "population": ward.population,
        "registered_phones": ward.registered_phones,
        "connectivity": ward.connectivity,
        "slope_deg": ward.slope_deg,
        "lithology": ward.lithology,
        "historical_events": ward.historical_events,
        "score": score.score,
        "level": score.level,
        "confidence": score.confidence,
        "crowd_uplift": score.crowd_uplift,
        "probability_24h": score.probability_24h,
        "population_at_risk": score.population_at_risk,
        "model_version": score.model_version,
        "factors": [f.to_dict() for f in score.factors],
        "inputs": {
            "rain_1h_mm": score.inputs.rain_1h_mm,
            "rain_24h_mm": score.inputs.rain_24h_mm,
            "rain_72h_mm": score.inputs.rain_72h_mm,
            "forecast_6h_mm": score.inputs.forecast_6h_mm,
            "soil_moisture": score.inputs.soil_moisture,
            "river_level_m": score.inputs.river_level_m,
            "gauge_online": score.inputs.gauge_online,
            "telemetry_age_minutes": score.inputs.telemetry_age_minutes,
            "open_reports": score.inputs.open_reports,
            "confirmed_reports": score.inputs.confirmed_reports,
        },
    }


async def ward_detail(db: AsyncSession, ward: Ward, score: WardScore) -> dict[str, Any]:
    """Full citizen/responder view for one ward, plus nearby assets."""
    payload = score_dict(ward, score)
    payload["polygon"] = ward.polygon or []
    payload["notes"] = ward.notes
    payload["children"] = ward.children
    payload["elderly"] = ward.elderly
    payload["disabled"] = ward.disabled
    payload["schools"] = ward.schools
    payload["health_centres"] = ward.health_centres
    payload["nearest_shelters"] = await nearby_shelters(db, ward)
    payload["recent_reports"] = await recent_reports(db, ward)
    payload["roads"] = await ward_roads(db, ward)
    payload["rainfall_series"] = await ingest.ward_rainfall_history(db, ward, hours=48)
    return payload


async def nearby_shelters(
    db: AsyncSession, ward: Ward, limit: int = 5
) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(Shelter).where(Shelter.status != "closed").limit(400)
    )
    shelters = list(rows.scalars().all())
    scored = [
        (geo.haversine_km(ward.latitude, ward.longitude, s.latitude, s.longitude), s)
        for s in shelters
    ]
    scored.sort(key=lambda pair: pair[0])
    return [
        {
            "code": s.code,
            "name": s.name,
            "kind": s.kind,
            "distance_km": round(distance, 2),
            "capacity": s.capacity,
            "occupied": s.occupied,
            "free_places": max(0, s.capacity - s.occupied),
            "has_medical": s.has_medical,
            "wheelchair_accessible": s.wheelchair_accessible,
            "status": s.status,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "manager_phone": s.manager_phone,
            "bearing_deg": round(
                geo.bearing_deg(ward.latitude, ward.longitude, s.latitude, s.longitude), 1
            ),
        }
        for distance, s in scored[:limit]
    ]


async def recent_reports(db: AsyncSession, ward: Ward, limit: int = 12) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=72)
    rows = await db.execute(
        select(HazardReport)
        .where(HazardReport.ward_id == ward.id, HazardReport.created_at >= since)
        .order_by(HazardReport.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "code": r.code,
            "hazard_type": r.hazard_type,
            "title": r.title,
            "description": r.description[:280],
            "status": r.status,
            "confidence": round(r.confidence, 3),
            "corroborated_by": r.corroborated_by,
            "self_severity": r.self_severity,
            "source": r.source,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "photo_url": f"/api/v1/media/{r.photo_path.split('/')[-1]}" if r.photo_path else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows.scalars()
    ]


async def ward_roads(db: AsyncSession, ward: Ward) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(RoadSegment).where(
            (RoadSegment.from_ward_id == ward.id) | (RoadSegment.to_ward_id == ward.id)
        )
    )
    return [
        {
            "code": r.code,
            "name": r.name,
            "status": r.status,
            "is_lifeline": r.is_lifeline,
            "length_km": round(r.length_km, 1),
            "note": r.note,
            "clearance_eta_hours": r.clearance_eta_hours,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows.scalars()
    ]


async def choropleth(db: AsyncSession, district_code: str | None = None) -> dict[str, Any]:
    """Single GeoJSON call for the map: ward *polygons* styled by live risk."""
    wards = await all_wards(db, district_code=district_code)
    scores = await live_scores(db, wards)
    features = []
    for ward in wards:
        score = scores[ward.id]
        ring = ward.polygon or _fallback_ring(ward)
        features.append(
            {
                "type": "Feature",
                "geometry": geo.ring_to_geojson([tuple(p) for p in ring]),
                "properties": {
                    "ward_id": ward.id,
                    "code": ward.code,
                    "name": ward.name,
                    "name_hi": ward.name_hi,
                    "district": ward.district.name if ward.district else "",
                    "score": score.score,
                    "level": score.level,
                    "confidence": score.confidence,
                    "probability_24h": score.probability_24h,
                    "population": ward.population,
                    "population_at_risk": score.population_at_risk,
                    "connectivity": ward.connectivity,
                    "latitude": ward.latitude,
                    "longitude": ward.longitude,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _fallback_ring(ward: Ward) -> list[list[float]]:
    """A ~1.4 km hexoid so a ward without a surveyed outline still renders."""
    import math

    pts = []
    for i in range(6):
        angle = math.pi / 3 * i
        lng = ward.longitude + 0.014 * math.cos(angle) / max(0.3, math.cos(math.radians(ward.latitude)))
        lat = ward.latitude + 0.013 * math.sin(angle)
        pts.append([round(lng, 5), round(lat, 5)])
    return pts


# --------------------------------------------------------------------------- #
# aggregate analytics
# --------------------------------------------------------------------------- #
async def analytics(db: AsyncSession) -> dict[str, Any]:
    wards = await all_wards(db)
    scores = await live_scores(db, wards)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    levels = {level: 0 for level in risk_engine.LEVEL_ORDER}
    exposed = 0
    confidences: list[float] = []
    for ward in wards:
        score = scores[ward.id]
        levels[score.level] = levels.get(score.level, 0) + 1
        exposed += score.population_at_risk
        confidences.append(score.confidence)

    alert_count = (
        await db.execute(
            select(func.count(Alert.id)).where(Alert.issued_at >= since)
        )
    ).scalar() or 0
    report_count = (
        await db.execute(
            select(func.count(HazardReport.id)).where(HazardReport.created_at >= since)
        )
    ).scalar() or 0
    verified_count = (
        await db.execute(
            select(func.count(HazardReport.id)).where(
                HazardReport.created_at >= since,
                HazardReport.status == "confirmed",
            )
        )
    ).scalar() or 0
    open_reports = (
        await db.execute(
            select(func.count(HazardReport.id)).where(
                HazardReport.status.in_(["new", "under_review"])
            )
        )
    ).scalar() or 0

    shelter_row = (
        await db.execute(
            select(
                func.count(Shelter.id),
                func.coalesce(func.sum(Shelter.capacity), 0),
                func.coalesce(func.sum(Shelter.occupied), 0),
            )
        )
    ).one()
    road_row = (
        await db.execute(
            select(
                func.count(RoadSegment.id),
                func.coalesce(
                    func.sum(case((RoadSegment.status == "closed", 1), else_=0)), 0
                ),
            )
        )
    ).one()
    district_count = (await db.execute(select(func.count(District.id)))).scalar() or 0
    telemetry_src = (
        await db.execute(
            select(TelemetryReading.source)
            .order_by(TelemetryReading.recorded_at.desc())
            .limit(1)
        )
    ).scalars().first() or "none"

    return {
        "wards": len(wards),
        "districts": int(district_count),
        "population_covered": sum(w.population for w in wards),
        "phones_reachable": sum(w.registered_phones for w in wards),
        "alerts_24h": int(alert_count),
        "reports_24h": int(report_count),
        "reports_verified_24h": int(verified_count),
        "open_reports": int(open_reports),
        "shelters": int(shelter_row[0]),
        "shelter_capacity": int(shelter_row[1] or 0),
        "shelter_occupied": int(shelter_row[2] or 0),
        "roads_closed": int(road_row[1] or 0),
        "roads_total": int(road_row[0]),
        "levels": levels,
        "population_exposed": int(exposed),
        "mean_confidence": round(statistics.fmean(confidences), 3) if confidences else 0.0,
        "median_lead_minutes": await lead_time_minutes(db),
        "telemetry_source": telemetry_src,
        "generated_at": datetime.now(timezone.utc),
    }


async def lead_time_minutes(db: AsyncSession) -> float | None:
    """Median minutes by which an automated warning *preceded* the first crowd
    report for the same ward.

    This is the number that actually distinguishes early warning from incident
    reporting, so it is computed rather than claimed. Returns ``None`` when
    there is no comparable pair — an empty result is reported honestly instead
    of as a zero.
    """
    alerts = await db.execute(
        select(Alert.ward_id, Alert.issued_at).where(Alert.auto_issued.is_(True))
    )
    leads: list[float] = []
    for ward_id, issued_at in alerts:
        if not ward_id or not issued_at:
            continue
        first_report = (
            await db.execute(
                select(func.min(HazardReport.created_at)).where(
                    HazardReport.ward_id == ward_id
                )
            )
        ).scalar()
        if not first_report:
            continue
        if first_report.tzinfo is None:
            first_report = first_report.replace(tzinfo=timezone.utc)
        stamp = issued_at if issued_at.tzinfo else issued_at.replace(tzinfo=timezone.utc)
        leads.append((first_report - stamp).total_seconds() / 60.0)
    if not leads:
        return None
    return round(statistics.median(leads), 1)


async def model_info(db: AsyncSession) -> dict[str, Any]:
    model = await active_model(db)
    weights = (model.weights if model else None) or dict(DEFAULT_WEIGHTS)
    thresholds = (model.thresholds if model else None) or dict(DEFAULT_THRESHOLDS)
    return {
        "version": MODEL_VERSION,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "thresholds": thresholds,
        "weights_sum": round(sum(weights.values()), 4),
        "crowd_uplift_cap": settings.crowd_uplift_cap,
        "active_config": model.version if model else "builtin-defaults",
        "factor_docs": [
            {
                "key": key,
                "weight": round(weights.get(key, 0.0), 4),
                **FACTOR_DOCS.get(key, {"name": key, "source": "", "kind": ""}),
            }
            for key in weights
        ],
        "disclaimer": (
            "Susceptibility prior, not a prediction of a specific slope failure. "
            "Weights encode published Himalayan landslide heuristics and local "
            "terrain priors; they are not fitted against a labelled event dataset, "
            "because no ward-level, time-aligned Uttarakhand event ledger exists. "
            "Treat orange/red as 'act now', and yellow as 'prepare'."
        ),
    }


async def timeseries(db: AsyncSession, hours: int = 24) -> list[dict[str, Any]]:
    """Hourly district roll-up for the console chart."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await db.execute(
        select(WardRisk)
        .where(WardRisk.computed_at >= since)
        .order_by(WardRisk.computed_at)
    )
    buckets: dict[str, dict[str, float]] = {}
    for record in rows.scalars():
        stamp = record.computed_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        key = stamp.strftime("%Y-%m-%dT%H:00Z")
        bucket = buckets.setdefault(
            key, {"max": 0.0, "sum": 0.0, "n": 0.0, "high": 0.0, "exposed": 0.0}
        )
        bucket["max"] = max(bucket["max"], record.score)
        bucket["sum"] += record.score
        bucket["n"] += 1
        bucket["exposed"] += record.population_at_risk
        if record.level in {"orange", "red"}:
            bucket["high"] += 1
    return [
        {
            "hour": key,
            "mean_score": round(v["sum"] / v["n"], 2) if v["n"] else 0.0,
            "max_score": round(v["max"], 2),
            "wards_high_alert": int(v["high"]),
            "population_exposed": int(v["exposed"]),
        }
        for key, v in sorted(buckets.items())
    ]


async def reachable_users(db: AsyncSession) -> int:
    rows = await db.execute(
        select(func.count(User.id)).where(User.phone.is_not(None), User.is_active.is_(True))
    )
    return int(rows.scalar() or 0)

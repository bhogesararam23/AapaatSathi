"""Risk endpoints: overview, per-ward detail, model transparency, sweeps, drills."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.core.deps import AdminOnly, DbSession, resolve_ward
from app.models import Ward, WardRisk
from app.schemas import ModelInfoOut, ScenarioIn, SweepOut
from app.services import alerts as alert_svc
from app.services import assembly, ingest, risk_engine

log = logging.getLogger("aapaatsathi.api.risk")

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/overview")
async def overview(
    db: DbSession,
    district: str | None = Query(default=None),
    min_score: float = Query(default=0.0, ge=0, le=100),
) -> dict[str, Any]:
    """Everything the watch-room grid and the map need in one call."""
    wards = await assembly.all_wards(db, district_code=district)
    if not wards:
        raise HTTPException(404, "No wards found")
    scores = await assembly.live_scores(db, wards)
    items = sorted(
        (assembly.score_dict(w, scores[w.id]) for w in wards),
        key=lambda d: d["score"],
        reverse=True,
    )
    visible = [i for i in items if i["score"] >= min_score]
    levels: dict[str, int] = {level: 0 for level in risk_engine.LEVEL_ORDER}
    for item in items:
        levels[item["level"]] = levels.get(item["level"], 0) + 1
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "wards": visible,
        "levels": levels,
        "population_exposed": sum(i["population_at_risk"] for i in items),
        "highest": items[0] if items else None,
        "mean_confidence": (
            round(sum(i["confidence"] for i in items) / len(items), 3) if items else 0.0
        ),
    }


@router.get("/model", response_model=ModelInfoOut)
async def model_info(db: DbSession) -> ModelInfoOut:
    """Published weights, thresholds and the honest limits of this model."""
    return ModelInfoOut.model_validate(await assembly.model_info(db))


@router.get("/leaderboard")
async def leaderboard(db: DbSession, limit: int = Query(default=10, ge=1, le=50)) -> dict:
    """Highest-risk wards right now — the first thing an operator should see."""
    wards = await assembly.all_wards(db)
    scores = await assembly.live_scores(db, wards)
    ranked = sorted(
        (assembly.score_dict(w, scores[w.id]) for w in wards),
        key=lambda d: d["score"],
        reverse=True,
    )[:limit]
    return {"wards": ranked}


@router.get("/history/{code}")
async def history(code: str, db: DbSession, limit: int = Query(default=60, ge=1, le=500)) -> dict:
    """Persisted score trajectory for one ward — replay any past run."""
    ward = await resolve_ward(db, code)
    rows = await db.execute(
        select(WardRisk)
        .where(WardRisk.ward_id == ward.id)
        .order_by(WardRisk.computed_at.desc())
        .limit(min(limit, 500))
    )
    records = list(rows.scalars().all())
    return {
        "ward_code": ward.code,
        "ward_name": ward.name,
        "points": [
            {
                "at": r.computed_at.isoformat() if r.computed_at else None,
                "score": r.score,
                "level": r.level,
                "confidence": r.confidence,
                "crowd_uplift": r.crowd_uplift,
                "population_at_risk": r.population_at_risk,
            }
            for r in reversed(records)
        ],
    }


@router.post("/sweep", response_model=SweepOut)
async def sweep(
    db: DbSession,
    admin: AdminOnly,
    district: str | None = Query(default=None),
    broadcast: bool = Query(default=True, description="Dispatch SMS/IVR on escalation"),
) -> SweepOut:
    """Recompute telemetry + risk now, and escalate anything that crossed a line."""
    # A district admin may only ever sweep their own district. Without this
    # clamp, `district=None` would let one district's officer broadcast state-
    # wide warnings — the same guard `POST /alerts` already enforces.
    district = _scoped_district(admin, district)
    wards = await assembly.all_wards(db, district_code=district)
    telemetry = await ingest.refresh_telemetry(db, wards)
    await db.commit()
    report = await alert_svc.run_sweep(db, wards, auto_broadcast=broadcast, actor_label=admin.full_name)
    await db.commit()
    return SweepOut(telemetry=telemetry, **report.to_dict())


def _scoped_district(user, requested: str | None) -> str | None:
    """Honour a requested district, except for non-system admins who get their own."""
    from app.models import Role

    if user.role == Role.SYSTEM_ADMIN.value:
        return requested
    if user.district is None:
        raise HTTPException(403, "Your account is not attached to a district")
    return user.district.code


@router.post("/scenario", response_model=dict)
async def scenario(body: ScenarioIn, db: DbSession, admin: AdminOnly) -> dict:
    """What-if / drill runner.

    Injects an operator-authored hyetograph for one ward, re-scores it and
    returns the resulting factor waterfall — without touching a real sensor or,
    unless ``broadcast`` is set, messaging anyone. This is the panel to drive on
    stage: push a ward from green to red in one request and watch the console
    react live.
    """
    ward = await resolve_ward(db, body.ward_code)
    from app.models import Role

    if admin.role != Role.SYSTEM_ADMIN.value and ward.district_id != admin.district_id:
        raise HTTPException(403, "That ward is outside your district")
    await ingest.inject_scenario(
        db,
        ward,
        rain_1h_mm=body.rain_1h_mm,
        rain_24h_mm=body.rain_24h_mm,
        rain_72h_mm=body.rain_72h_mm,
        forecast_6h_mm=body.forecast_6h_mm,
        soil_moisture=body.soil_moisture,
    )
    await db.commit()

    fresh = (await db.execute(select(Ward).where(Ward.id == ward.id))).scalars().one()
    # When the operator asks to exercise the escalation path, do not persist this
    # preview score first: the sweep compares against the last persisted level, and
    # writing it here would make the escalation look like a no-op.
    scores = await assembly.live_scores(db, [fresh], persist=not body.broadcast)
    await db.commit()
    score = scores[fresh.id]
    payload = assembly.score_dict(fresh, score)

    escalation = None
    if body.broadcast and score.level in {"yellow", "orange", "red"}:
        report = await alert_svc.run_sweep(
            db, [fresh], auto_broadcast=True, actor_label=f"{admin.full_name} (scenario)"
        )
        await db.commit()
        escalation = report.to_dict()

    return {
        "ward": payload,
        "note": (
            "Scenario telemetry is tagged source='scenario' and is never "
            "presented as an observation."
        ),
        "escalation": escalation,
    }

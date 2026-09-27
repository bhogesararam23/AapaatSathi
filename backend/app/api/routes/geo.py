"""Geography and map read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.core.deps import DbSession, resolve_ward
from app.models import District, RainGauge, Ward
from app.schemas import DistrictOut, WardOut
from app.services import assembly, ingest

router = APIRouter(tags=["geography"])


@router.get("/districts", response_model=list[DistrictOut])
async def districts(db: DbSession) -> list[DistrictOut]:
    rows = await db.execute(select(District).order_by(District.code))
    return [DistrictOut.model_validate(d) for d in rows.scalars()]


@router.get("/wards", response_model=list[WardOut])
async def wards(
    db: DbSession,
    district: str | None = Query(default=None, description="District code, e.g. DEH"),
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[WardOut]:
    stmt = select(Ward).order_by(Ward.code).limit(min(limit, 2000))
    if district:
        stmt = stmt.join(District, Ward.district_id == District.id).where(
            District.code == district.strip().upper()
        )
    rows = await db.execute(stmt)
    return [WardOut.model_validate(w) for w in rows.scalars()]


@router.get("/wards/{code}", response_model=dict)
async def ward_detail(code: str, db: DbSession) -> dict:
    ward = await resolve_ward(db, code)
    scores = await assembly.live_scores(db, [ward])
    return await assembly.ward_detail(db, ward, scores[ward.id])


@router.get("/geo/choropleth")
async def choropleth(
    db: DbSession,
    district: str | None = Query(default=None),
) -> dict:
    """One request, whole map: ward polygons styled by live risk level."""
    payload = await assembly.choropleth(db, district_code=district)
    if not payload["features"]:
        raise HTTPException(404, "No wards for that district")
    return payload


@router.get("/geo/wards/{code}/series")
async def ward_series(code: str, db: DbSession, hours: int = Query(default=48, ge=6, le=96)) -> dict:
    ward = await resolve_ward(db, code)
    scores = await assembly.live_scores(db, [ward])
    score = scores[ward.id]
    rows = await db.execute(
        select(RainGauge).where(RainGauge.ward_id == ward.id)
    )
    return {
        "ward_code": ward.code,
        "ward_name": ward.name,
        "rainfall": await ingest.ward_rainfall_history(db, ward, hours=hours),
        "current": assembly.score_dict(ward, score),
        "gauges": [
            {
                "code": g.code,
                "name": g.name,
                "kind": g.kind,
                "status": g.status,
                "last_seen_at": g.last_seen_at.isoformat() if g.last_seen_at else None,
            }
            for g in rows.scalars()
        ],
    }

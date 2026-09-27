"""Response assets: shelters, road status and deployable resources.

Warning alone does not save a village — people need somewhere to go and need to
know which road is still open. These endpoints keep that operational picture
current, and every write is actor-attributed because during a real event the
question "who marked this road open?" gets asked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.core.deps import AnyStaff, DbSession, resolve_ward
from app.core.events import OPS, PUBLIC, manager
from app.core.security import generate_code
from app.models import (
    AuditLog,
    District,
    ResourceUnit,
    RiskLevel,
    RoadSegment,
    RoadStatus,
    Shelter,
    ShelterStatus,
    Ward,
)
from app.schemas import (
    ResourceOut,
    RoadOut,
    RoadUpdateIn,
    ShelterCreateIn,
    ShelterOut,
    ShelterUpdateIn,
)
from app.services import geo

router = APIRouter(tags=["response assets"])


def _shelter_payload(s: Shelter, ward: Ward | None, distance_km: float | None = None) -> dict[str, Any]:
    return {
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "ward_id": s.ward_id,
        "ward_name": ward.name if ward else None,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "kind": s.kind,
        "capacity": s.capacity,
        "occupied": s.occupied,
        "staff": s.staff,
        "has_medical": s.has_medical,
        "has_generator": s.has_generator,
        "wheelchair_accessible": s.wheelchair_accessible,
        "water_security_days": s.water_security_days,
        "manager_name": s.manager_name,
        "manager_phone": s.manager_phone,
        "status": s.status,
        "free_places": max(0, s.capacity - s.occupied),
        "occupancy_pct": round(100 * s.occupied / s.capacity, 1) if s.capacity else 0.0,
        "distance_km": round(distance_km, 2) if distance_km is not None else None,
        "last_updated_at": s.last_updated_at,
    }


def _derive_status(occupied: int, capacity: int, current: str) -> str:
    if current == ShelterStatus.CLOSED.value:
        return ShelterStatus.CLOSED.value
    if capacity <= 0:
        return ShelterStatus.CLOSED.value
    ratio = occupied / capacity
    if ratio >= 1.0:
        return ShelterStatus.OVERFLOW.value
    if ratio >= 0.85:
        return ShelterStatus.NEAR_FULL.value
    return ShelterStatus.OPEN.value


@router.get("/shelters")
async def list_shelters(
    db: DbSession,
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    district: str | None = None,
    ward: str | None = None,
    only_space: bool = Query(default=False, description="Hide full and closed shelters"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    stmt = select(Shelter)
    if district:
        stmt = stmt.join(District, Shelter.district_id == District.id).where(
            District.code == district.strip().upper()
        )
    if ward:
        target = await resolve_ward(db, ward)
        stmt = stmt.where(Shelter.ward_id == target.id)
    rows = await db.execute(stmt.limit(min(limit, 1000)))
    shelters = list(rows.scalars().all())

    ward_ids = {s.ward_id for s in shelters if s.ward_id}
    wards = {}
    if ward_ids:
        wrows = await db.execute(select(Ward).where(Ward.id.in_(list(ward_ids))))
        wards = {w.id: w for w in wrows.scalars()}

    items = []
    for shelter in shelters:
        distance = None
        if lat is not None and lng is not None:
            distance = geo.haversine_km(lat, lng, shelter.latitude, shelter.longitude)
        items.append((distance if distance is not None else 1e9, shelter, distance, wards.get(shelter.ward_id)))
    items.sort(key=lambda t: t[0])

    payload = [_shelter_payload(s, w, d) for _, s, d, w in items]
    if only_space:
        payload = [p for p in payload if p["free_places"] > 0 and p["status"] != "closed"]
    return {
        "count": len(payload),
        "total_capacity": sum(p["capacity"] for p in payload),
        "total_free": sum(p["free_places"] for p in payload),
        "shelters": payload,
    }


@router.post("/shelters", status_code=201)
async def create_shelter(body: ShelterCreateIn, db: DbSession, staff: AnyStaff) -> dict[str, Any]:
    ward = await resolve_ward(db, body.ward_code)
    code = generate_code("SH")
    lat = body.latitude or ward.latitude
    lng = body.longitude or ward.longitude
    shelter = Shelter(
        code=code,
        name=body.name,
        ward_id=ward.id,
        district_id=ward.district_id,
        latitude=lat,
        longitude=lng,
        kind=body.kind,
        capacity=body.capacity,
        has_medical=body.has_medical,
        has_generator=body.has_generator,
        wheelchair_accessible=body.wheelchair_accessible,
        manager_name=body.manager_name,
        manager_phone=body.manager_phone,
    )
    db.add(shelter)
    await db.flush()
    db.add(
        AuditLog(
            actor_id=staff.id,
            actor_label=staff.full_name,
            action="shelter.create",
            entity="shelter",
            entity_id=code,
        )
    )
    await manager.publish("shelter:new", {"code": code, "name": body.name}, channel=PUBLIC)
    return _shelter_payload(shelter, ward)


@router.patch("/shelters/{code}")
async def update_shelter(
    code: str, body: ShelterUpdateIn, db: DbSession, staff: AnyStaff
) -> dict[str, Any]:
    rows = await db.execute(select(Shelter).where(Shelter.code == code))
    shelter = rows.scalars().first()
    if not shelter:
        raise HTTPException(404, f"No shelter '{code}'")

    before = {"occupied": shelter.occupied, "capacity": shelter.capacity, "status": shelter.status}
    if body.occupied is not None:
        shelter.occupied = body.occupied
    if body.capacity is not None:
        shelter.capacity = body.capacity
    if body.staff is not None:
        shelter.staff = body.staff
    if body.water_security_days is not None:
        shelter.water_security_days = body.water_security_days
    if body.status is not None:
        shelter.status = body.status
    shelter.status = _derive_status(shelter.occupied, shelter.capacity, shelter.status)
    await db.flush()
    after = {"occupied": shelter.occupied, "capacity": shelter.capacity, "status": shelter.status}

    db.add(
        AuditLog(
            actor_id=staff.id,
            actor_label=staff.full_name,
            action="shelter.update",
            entity="shelter",
            entity_id=code,
            detail={"before": before, "after": after, "note": body.note or ""},
        )
    )
    await manager.publish(
        "shelter:update",
        {
            "code": code,
            "name": shelter.name,
            "occupied": shelter.occupied,
            "capacity": shelter.capacity,
            "free_places": max(0, shelter.capacity - shelter.occupied),
            "status": shelter.status,
        },
        channel=PUBLIC,
    )
    ward = await db.get(Ward, shelter.ward_id) if shelter.ward_id else None
    return _shelter_payload(shelter, ward)


# --------------------------------------------------------------------------- #
# roads
# --------------------------------------------------------------------------- #
async def _road_names(db: AsyncSession, roads: list[RoadSegment]) -> list[dict[str, Any]]:
    ids = {r.from_ward_id for r in roads} | {r.to_ward_id for r in roads}
    ids.discard(None)
    wards: dict[int, Ward] = {}
    if ids:
        rows = await db.execute(select(Ward).where(Ward.id.in_(list(ids))))
        wards = {w.id: w for w in rows.scalars()}
    districts: dict[int, District] = {}
    dids = {r.district_id for r in roads if r.district_id}
    if dids:
        rows = await db.execute(select(District).where(District.id.in_(list(dids))))
        districts = {d.id: d for d in rows.scalars()}
    out = []
    for r in roads:
        out.append(
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "district_id": r.district_id,
                "district_name": districts[r.district_id].name if r.district_id in districts else None,
                "from_ward_id": r.from_ward_id,
                "to_ward_id": r.to_ward_id,
                "from_ward_name": wards[r.from_ward_id].name if r.from_ward_id in wards else None,
                "to_ward_name": wards[r.to_ward_id].name if r.to_ward_id in wards else None,
                "polyline": r.polyline or [],
                "length_km": round(r.length_km, 1),
                "status": r.status,
                "is_lifeline": r.is_lifeline,
                "note": r.note,
                "clearance_eta_hours": r.clearance_eta_hours,
                "updated_at": r.updated_at,
            }
        )
    return out


@router.get("/roads")
async def list_roads(
    db: DbSession,
    district: str | None = None,
    status: str | None = None,
    blocked_only: bool = Query(default=False),
) -> dict[str, Any]:
    stmt = select(RoadSegment).order_by(RoadSegment.name)
    if district:
        stmt = stmt.join(District, RoadSegment.district_id == District.id).where(
            District.code == district.strip().upper()
        )
    if status:
        stmt = stmt.where(RoadSegment.status == status)
    if blocked_only:
        stmt = stmt.where(RoadSegment.status.in_([RoadStatus.CLOSED.value, RoadStatus.PARTIAL.value]))
    rows = await db.execute(stmt)
    roads = list(rows.scalars().all())
    payload = await _road_names(db, roads)
    tally: dict[str, int] = {s.value: 0 for s in RoadStatus}
    for road in roads:
        tally[road.status] = tally.get(road.status, 0) + 1
    return {
        "count": len(payload),
        "by_status": tally,
        "lifelines_blocked": sum(
            1 for r in payload if r["is_lifeline"] and r["status"] in {"closed", "partial"}
        ),
        "roads": payload,
    }


@router.patch("/roads/{code}/status")
async def update_road(
    code: str, body: RoadUpdateIn, db: DbSession, staff: AnyStaff
) -> dict[str, Any]:
    rows = await db.execute(select(RoadSegment).where(RoadSegment.code == code))
    road = rows.scalars().first()
    if not road:
        raise HTTPException(404, f"No road segment '{code}'")
    previous = road.status
    road.status = body.status
    road.note = body.note[:500]
    road.clearance_eta_hours = body.clearance_eta_hours
    road.updated_by_id = staff.id
    await db.flush()
    db.add(
        AuditLog(
            actor_id=staff.id,
            actor_label=staff.full_name,
            action="road.status",
            entity="road",
            entity_id=code,
            detail={"from": previous, "to": body.status, "note": body.note},
        )
    )
    await manager.publish(
        "road:update",
        {
            "code": code,
            "name": road.name,
            "status": body.status,
            "is_lifeline": road.is_lifeline,
            "clearance_eta_hours": body.clearance_eta_hours,
            "note": body.note,
            "updated_by": staff.full_name,
        },
        channel=PUBLIC,
    )
    return {"code": code, "status": body.status, "previous": previous}


# --------------------------------------------------------------------------- #
# resources
# --------------------------------------------------------------------------- #
@router.get("/resources", response_model=list[ResourceOut])
async def list_resources(
    db: DbSession,
    kind: str | None = None,
    ward: str | None = None,
) -> list[ResourceOut]:
    stmt = select(ResourceUnit).order_by(ResourceUnit.kind)
    if kind:
        stmt = stmt.where(ResourceUnit.kind == kind)
    rows = await db.execute(stmt)
    units = list(rows.scalars().all())
    if ward:
        target = await resolve_ward(db, ward)
        units = [u for u in units if u.ward_id == target.id]
    return [ResourceOut.model_validate(u) for u in units]


@router.patch("/resources/{code}/status")
async def update_resource(
    code: str,
    db: DbSession,
    staff: AnyStaff,
    status: str = Query(..., description="standby | enroute | deployed | returning | unavailable"),
    ward_code: str | None = Query(default=None),
    eta_hours: float | None = Query(default=None, ge=0, le=72),
) -> dict[str, Any]:
    rows = await db.execute(select(ResourceUnit).where(ResourceUnit.code == code))
    unit = rows.scalars().first()
    if not unit:
        raise HTTPException(404, f"No resource '{code}'")
    unit.status = status
    unit.eta_hours = eta_hours
    if ward_code:
        target = await resolve_ward(db, ward_code)
        unit.ward_id = target.id
        unit.district_id = target.district_id
    await db.flush()
    db.add(
        AuditLog(
            actor_id=staff.id,
            actor_label=staff.full_name,
            action="resource.status",
            entity="resource",
            entity_id=code,
            detail={"status": status, "ward": ward_code},
        )
    )
    await manager.publish(
        "resource:update",
        {"code": code, "name": unit.name, "status": status, "kind": unit.kind},
        channel=OPS,
    )
    return {"code": code, "status": unit.status, "ward_id": unit.ward_id}

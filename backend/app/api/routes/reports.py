"""Crowd-sourced hazard reports.

Ground truth from the hillside is the signal the model cannot get from any
satellite — a crack appearing on the approach road, a spring turning muddy, a
tree starting to lean. It is also the signal most easily abused, so every
report carries an explicit, *explainable* confidence rather than being trusted
or discarded. Confidence is a published weighted blend of reporter history,
independent corroboration, evidence attached and geometric plausibility, and
the components ship in the API response so a reviewer can see why a report was
believed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select

from app.config import settings
from app.core.deps import AnyStaff, DbSession, MaybeUser, resolve_ward
from app.core.events import OPS, manager
from app.core.security import generate_code
from app.models import AuditLog, District, HazardReport, ReportSource, ReportStatus, Role, User, Ward
from app.schemas import ReportCreateIn, ReportNearbyIn, ReportOut, ReportVerdictIn
from app.services import geo, i18n

log = logging.getLogger("aapaatsathi.api.reports")

router = APIRouter(prefix="/reports", tags=["reports"])

MAX_PHOTO_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MATCH_RADIUS_KM = 1.2

# Published confidence weights (sum = 1.0)
CONF_WEIGHTS = {
    "reporter_trust": 0.30,
    "corroboration": 0.25,
    "evidence": 0.20,
    "severity_signal": 0.15,
    "geo_plausibility": 0.10,
}


async def locate_ward(db, lat: float, lng: float) -> Ward | None:
    """Polygon containment first, then nearest centroid within 8 km."""
    rows = await db.execute(select(Ward))
    wards = list(rows.scalars().all())
    for ward in wards:
        ring = [(float(p[0]), float(p[1])) for p in (ward.polygon or [])]
        if len(ring) >= 3 and geo.point_in_polygon(lat, lng, ring):
            return ward
    best = None
    for ward in wards:
        d = geo.haversine_km(lat, lng, ward.latitude, ward.longitude)
        if d <= 8.0 and (best is None or d < best[0]):
            best = (d, ward)
    return best[1] if best else None


def compute_confidence(
    *,
    reporter_trust: float,
    corroborated_by: int,
    has_photo: bool,
    is_verified_reporter: bool,
    self_severity: int,
    accuracy_m: float,
    distance_from_ward_km: float,
) -> dict[str, Any]:
    """Transparency over cleverness: return the parts, not just the number."""
    parts = {
        "reporter_trust": max(0.0, min(1.0, reporter_trust)),
        "corroboration": min(1.0, max(0, corroborated_by - 1) / 4.0),
        "evidence": (0.6 if has_photo else 0.0) + (0.4 if is_verified_reporter else 0.0),
        "severity_signal": max(0.0, min(1.0, (self_severity - 1) / 4.0)),
        "geo_plausibility": max(0.0, 1.0 - (distance_from_ward_km / 8.0))
        * (1.0 if 0 < accuracy_m <= 100 else 0.6 if accuracy_m <= 500 else 0.3),
    }
    total = round(sum(CONF_WEIGHTS[k] * parts[k] for k in CONF_WEIGHTS), 4)
    return {
        "value": total,
        "components": {k: round(v, 3) for k, v in parts.items()},
        "weights": CONF_WEIGHTS,
    }


async def _photo_name(save: Path, upload: UploadFile) -> str | None:
    content_type = (upload.content_type or "").lower()
    if content_type and content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported image type '{content_type}'")
    blob = await upload.read()
    if not blob:
        return None
    if len(blob) > MAX_PHOTO_BYTES:
        raise HTTPException(413, f"Photo exceeds {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    save.mkdir(parents=True, exist_ok=True)
    ext = {"image/png": ".png", "image/webp": ".webp", "image/heic": ".heic"}.get(content_type, ".jpg")
    name = f"{uuid.uuid4().hex}{ext}"
    (save / name).write_bytes(blob)
    return name


def _serialize(report: HazardReport, ward: Ward | None = None) -> dict[str, Any]:
    data = ReportOut.model_validate(report).model_dump()
    data["photo_url"] = f"/api/v1/media/{Path(report.photo_path).name}" if report.photo_path else None
    if ward:
        data["ward_name"] = ward.name
        data["district_name"] = ward.district.name if ward.district else None
    # Never surface the reporter's identity on a public hazard feed.
    data["reporter_alias"] = "Resident" if not report.reporter_id else "Verified resident"
    return data


@router.post("", status_code=201)
async def create_report(
    db: DbSession,
    user: MaybeUser,
    hazard_type: str = Form("landslide"),
    title: str = Form(""),
    description: str = Form(""),
    latitude: float = Form(...),
    longitude: float = Form(...),
    accuracy_m: float = Form(0.0),
    self_severity: int = Form(3),
    ward_code: str | None = Form(None),
    lang: str = Form("en"),
    consent_media: bool = Form(False),
    photo: UploadFile | None = File(None),
) -> dict[str, Any]:
    """File a hazard. Works anonymously — a tourist with no account on the
    Mussoorie road should still be able to report a slide."""
    if hazard_type not in i18n.HAZARD_NAMES:
        raise HTTPException(422, f"Unknown hazard type '{hazard_type}'")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(422, "Coordinates out of range")

    ward = await resolve_ward(db, ward_code) if ward_code else await locate_ward(db, latitude, longitude)
    if ward is None:
        raise HTTPException(422, "Location is outside the covered ward map")

    photo_name = (
        await _photo_name(Path(settings.media_dir), photo) if photo is not None else None
    )
    distance = geo.haversine_km(latitude, longitude, ward.latitude, ward.longitude)

    # Corroboration: an existing open report of the same hazard within 1.2 km
    # merges into it rather than creating a duplicate cluster on the map.
    near_window = datetime.now(timezone.utc) - timedelta(hours=48)
    existing_rows = await db.execute(
        select(HazardReport).where(
            HazardReport.hazard_type == hazard_type,
            HazardReport.created_at >= near_window,
            HazardReport.status.in_([ReportStatus.NEW.value, ReportStatus.UNDER_REVIEW.value, ReportStatus.CONFIRMED.value]),
        )
    )
    match = None
    for candidate in existing_rows.scalars():
        if geo.haversine_km(latitude, longitude, candidate.latitude, candidate.longitude) <= MATCH_RADIUS_KM:
            if user and candidate.reporter_id == user.id:
                raise HTTPException(409, "You already reported this nearby")
            match = candidate
            break

    if match is not None:
        match.corroborated_by = (match.corroborated_by or 1) + 1
        if photo_name and not match.photo_path:
            match.photo_path = photo_name
        # Corroboration is only as strong as its least-trusted author, so take
        # the *best* available reporter signal rather than the newcomer's alone.
        prior_trust = _reporter_trust(None)
        if match.reporter_id:
            original = await db.get(User, match.reporter_id)
            prior_trust = _reporter_trust(original)
        conf = compute_confidence(
            reporter_trust=max(_reporter_trust(user), prior_trust),
            corroborated_by=match.corroborated_by,
            has_photo=bool(match.photo_path),
            is_verified_reporter=bool((user and user.is_verified)),
            self_severity=max(match.self_severity, self_severity),
            accuracy_m=accuracy_m or match.accuracy_m,
            distance_from_ward_km=distance,
        )
        match.confidence = conf["value"]
        await db.flush()
        await manager.publish("report:corroborated", {"code": match.code, "by": match.corroborated_by}, channel=OPS)
        return {
            "merged": True,
            "report": _serialize(match, ward),
            "confidence": conf,
            "message": i18n.localize(
                "report.received", i18n.normalize_lang(lang), code=match.code, ward=ward.name
            ),
        }

    code = generate_code("HR")
    report = HazardReport(
        code=code,
        ward_id=ward.id,
        district_id=ward.district_id,
        reporter_id=user.id if user else None,
        hazard_type=hazard_type,
        title=(title or i18n.hazard_name(hazard_type, "en")).strip()[:160],
        description=(description or "").strip()[:2000],
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy_m,
        photo_path=photo_name,
        self_severity=max(1, min(5, self_severity)),
        status=ReportStatus.NEW.value,
        source=ReportSource.WEB.value if user else ReportSource.SMS.value,
        corroborated_by=1,
    )
    conf = compute_confidence(
        reporter_trust=_reporter_trust(user),
        corroborated_by=1,
        has_photo=bool(photo_name),
        is_verified_reporter=bool(user and user.is_verified),
        self_severity=report.self_severity,
        accuracy_m=accuracy_m,
        distance_from_ward_km=distance,
    )
    report.confidence = conf["value"]
    db.add(report)
    await db.flush()

    db.add(
        AuditLog(
            actor_id=user.id if user else None,
            actor_label=user.full_name if user else "anonymous",
            action="report.create",
            entity="hazard_report",
            entity_id=code,
            detail={"ward": ward.code, "hazard": hazard_type, "confidence": conf["value"]},
        )
    )
    await manager.publish(
        "report:new",
        {
            "code": code,
            "hazard_type": hazard_type,
            "title": report.title,
            "ward": ward.name,
            "ward_code": ward.code,
            "district_id": ward.district_id,
            "latitude": latitude,
            "longitude": longitude,
            "confidence": conf["value"],
            "self_severity": report.self_severity,
            "photo_url": f"/api/v1/media/{photo_name}" if photo_name else None,
            "created_at": report.created_at.isoformat(),
        },
        channel=OPS,
    )
    return {
        "merged": False,
        "report": _serialize(report, ward),
        "confidence": conf,
        "message": i18n.localize(
            "report.received", i18n.normalize_lang(lang), code=code, ward=ward.name
        ),
    }


def _reporter_trust(user: User | None) -> float:
    if user is None:
        return 0.35  # anonymous is not disbelieved, just weighted lower
    return max(0.0, min(1.0, user.trust_score))


@router.get("")
async def list_reports(
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    ward: str | None = None,
    hazard_type: str | None = None,
    needs_review: bool = Query(default=False, description="Staff triage queue"),
    since_hours: int = Query(default=168, ge=1, le=24 * 90),
    limit: int = Query(default=100, ge=1, le=400),
) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    stmt = (
        select(HazardReport)
        .where(HazardReport.created_at >= cutoff)
        .order_by(HazardReport.confidence.desc(), HazardReport.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(HazardReport.status == status_filter)
    if hazard_type:
        stmt = stmt.where(HazardReport.hazard_type == hazard_type)
    if needs_review:
        stmt = stmt.where(HazardReport.status.in_([ReportStatus.NEW.value, ReportStatus.UNDER_REVIEW.value]))
    target_ward = None
    if ward:
        target_ward = await resolve_ward(db, ward)
        stmt = stmt.where(HazardReport.ward_id == target_ward.id)

    rows = await db.execute(stmt.limit(min(limit, 400)))
    reports = list(rows.scalars().all())
    ward_ids = {r.ward_id for r in reports if r.ward_id}
    wards = {}
    if ward_ids:
        wrows = await db.execute(select(Ward).where(Ward.id.in_(list(ward_ids))))
        wards = {w.id: w for w in wrows.scalars()}
    return {
        "count": len(reports),
        "reports": [_serialize(r, wards.get(r.ward_id)) for r in reports],
    }


@router.get("/stats")
async def report_stats(db: DbSession) -> dict[str, Any]:
    rows = await db.execute(
        select(HazardReport.status, func.count(HazardReport.id)).group_by(HazardReport.status)
    )
    by_status = {status: int(count) for status, count in rows}
    kinds = await db.execute(
        select(HazardReport.hazard_type, func.count(HazardReport.id)).group_by(
            HazardReport.hazard_type
        )
    )
    return {
        "by_status": by_status,
        "by_hazard": {k: int(c) for k, c in kinds},
        "total": sum(by_status.values()),
    }


@router.post("/nearby")
async def nearby(body: ReportNearbyIn, db: DbSession) -> dict[str, Any]:
    rows = await db.execute(
        select(HazardReport).where(
            HazardReport.status.notin_([ReportStatus.DISMISSED.value, ReportStatus.RESOLVED.value])
        )
    )
    found = [
        r for r in rows.scalars()
        if geo.haversine_km(body.latitude, body.longitude, r.latitude, r.longitude) <= body.radius_km
    ]
    return {
        "count": len(found),
        "radius_km": body.radius_km,
        "reports": [_serialize(r) for r in found[:50]],
    }


@router.get("/{code}")
async def get_report(code: str, db: DbSession) -> dict[str, Any]:
    rows = await db.execute(select(HazardReport).where(HazardReport.code == code))
    report = rows.scalars().first()
    if not report:
        raise HTTPException(404, f"No report '{code}'")
    ward = await db.get(Ward, report.ward_id) if report.ward_id else None
    payload = _serialize(report, ward)
    payload["confidence_components"] = {
        "weights": CONF_WEIGHTS,
        "corroborated_by": report.corroborated_by,
        "has_photo": bool(report.photo_path),
    }
    return payload


@router.patch("/{code}/verdict")
async def verdict(
    code: str, body: ReportVerdictIn, db: DbSession, staff: AnyStaff
) -> dict[str, Any]:
    """Confirm or dismiss with a note — this is what retrains reporter trust."""
    rows = await db.execute(select(HazardReport).where(HazardReport.code == code))
    report = rows.scalars().first()
    if not report:
        raise HTTPException(404, f"No report '{code}'")
    report.status = body.status
    report.resolution_note = body.note[:1000]
    if body.status in {ReportStatus.CONFIRMED.value, ReportStatus.DISMISSED.value}:
        report.verified_by_id = staff.id
        report.verified_at = datetime.now(timezone.utc)
    if body.status == ReportStatus.CONFIRMED.value:
        report.confidence = max(report.confidence, 0.9)
        if report.reporter_id:
            reporter = await db.get(User, report.reporter_id)
            if reporter:
                reporter.trust_score = min(1.0, round(reporter.trust_score + 0.06, 4))
    if body.status == ReportStatus.DISMISSED.value and report.reporter_id:
        reporter = await db.get(User, report.reporter_id)
        if reporter:
            reporter.trust_score = max(0.05, round(reporter.trust_score - 0.10, 4))

    db.add(
        AuditLog(
            actor_id=staff.id,
            actor_label=staff.full_name,
            action=f"report.{body.status}",
            entity="hazard_report",
            entity_id=code,
            detail={"note": body.note[:200]},
        )
    )
    await db.flush()
    await manager.publish(
        "report:verdict",
        {"code": code, "status": body.status, "by": staff.full_name},
        channel=OPS,
    )
    return {"report": _serialize(report), "message": f"Marked {body.status}"}


@router.post("/{code}/corroborate")
async def corroborate(code: str, db: DbSession, user: MaybeUser) -> dict[str, Any]:
    """"I can see it too" — the low-effort path that drives corroboration up."""
    rows = await db.execute(select(HazardReport).where(HazardReport.code == code))
    report = rows.scalars().first()
    if not report:
        raise HTTPException(404, f"No report '{code}'")
    if user and report.reporter_id == user.id:
        raise HTTPException(400, "You filed this report yourself")
    report.corroborated_by = (report.corroborated_by or 1) + 1
    report.confidence = min(
        1.0,
        round(report.confidence + 0.09 * (1.0 if (report.corroborated_by or 1) <= 3 else 0.4), 4),
    )
    await db.flush()
    await manager.publish("report:corroborated", {"code": code, "by": report.corroborated_by}, channel=OPS)
    return {"code": code, "corroborated_by": report.corroborated_by, "confidence": report.confidence}


@router.post("/{code}/dispatch")
async def dispatch(code: str, db: DbSession, staff: AnyStaff) -> dict[str, Any]:
    """Task a report to a field team."""
    rows = await db.execute(select(HazardReport).where(HazardReport.code == code))
    report = rows.scalars().first()
    if not report:
        raise HTTPException(404, f"No report '{code}'")
    report.responders_dispatched = (report.responders_dispatched or 0) + 1
    report.status = ReportStatus.UNDER_REVIEW.value
    db.add(
        AuditLog(
            actor_id=staff.id,
            actor_label=staff.full_name,
            action="report.dispatch",
            entity="hazard_report",
            entity_id=code,
        )
    )
    await db.flush()
    return {"code": code, "responders_dispatched": report.responders_dispatched}

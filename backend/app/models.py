"""ORM models.

Design notes for reviewers
--------------------------
* Every many-to-one relationship uses ``lazy="selectin"`` and **no** one-to-many
  back-references are declared. That keeps the app fully async-safe (no
  ``MissingGreenlet`` surprises) and prevents load recursion, at the cost of a
  little extra fetching. Collections are loaded with explicit ``select()`` in
  the API layer instead.
* ``JSON`` columns carry model outputs (factor breakdowns, template payloads).
  Storing the breakdown is what makes the score auditable after the fact — a
  judge, a collector or an inquiry commission can see *why* a ward scored 87.
* Integer PKs are internal only; anything a human reads uses a ``code`` column.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Role(str, enum.Enum):
    CITIZEN = "citizen"
    FIELD_RESPONDER = "field_responder"
    DISTRICT_ADMIN = "district_admin"
    SYSTEM_ADMIN = "system_admin"


class RiskLevel(str, enum.Enum):
    GREEN = "green"
    BLUE = "blue"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


HAZARD_LABEL: dict[str, str] = {
    "landslide": "Landslide",
    "flash_flood": "Flash flood",
    "road_block": "Road blockage",
    "debris_flow": "Debris flow",
    "cloudburst": "Cloudburst",
    "earthquake": "Seismic activity",
    "glacial_lake": "Glacial lake risk",
    "water_logging": "Waterlogging",
}


class ReportStatus(str, enum.Enum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class ReportSource(str, enum.Enum):
    APP = "app"
    WEB = "web"
    SMS = "sms"
    IVR = "ivr"
    FIELD = "field"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Channel(str, enum.Enum):
    SMS = "sms"
    IVR = "ivr"
    PUSH = "push"
    INAPP = "inapp"


class NotificationStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    SIMULATED = "simulated"
    FAILED = "failed"


class RoadStatus(str, enum.Enum):
    OPEN = "open"
    CAUTION = "caution"
    PARTIAL = "partial"
    CLOSED = "closed"


class ShelterStatus(str, enum.Enum):
    OPEN = "open"
    NEAR_FULL = "near_full"
    OVERFLOW = "overflow"
    CLOSED = "closed"


class Lithology(str, enum.Enum):
    """Rock classes ordered roughly by slope instability in the Middle Himalaya."""

    SIWALIK = "siwalik"                 # young, unconsolidated, very unstable
    LESSER_HIMALAYA = "lesser_himalaya"  # phyllite/slate, fault-bounded
    GREATER_HIMALAYA = "greater_himalaya"
    TETHYS_HIMALAYA = "tethys_himalaya"
    ALLUVIUM = "alluvium"
    GRANITE_GNEISS = "granite_gneiss"


# --------------------------------------------------------------------------- #
# Geography
# --------------------------------------------------------------------------- #
class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_hi: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(40), default="Uttarakhand")
    headquarters: Mapped[str] = mapped_column(String(60), default="")
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    area_km2: Mapped[float] = mapped_column(Float, default=0.0)
    population: Mapped[int] = mapped_column(Integer, default=0)
    control_room: Mapped[str] = mapped_column(String(40), default="1070")
    collector_phone: Mapped[str] = mapped_column(String(40), default="")
    ndrf_base: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # No ``wards`` relationship: nothing reads it, districts are never deleted,
    # and a one-to-many here would need a back-reference that risks load
    # recursion in an async session. Fetch wards with an explicit select instead.


class Ward(Base):
    """The unit of warning.

    District-level alerts fail in the hills because a slope is a few hundred
    metres wide. A ward here means the smallest revenue/GRG unit we can put a
    population number and a coordinate on.
    """

    __tablename__ = "wards"
    __table_args__ = (
        UniqueConstraint("code", name="uq_ward_code"),
        Index("ix_ward_district", "district_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(90))
    name_hi: Mapped[str] = mapped_column(String(90), default="")
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True)

    # geometry ------------------------------------------------------------- #
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    polygon: Mapped[list[Any] | None] = mapped_column(JSON, default=list)

    # terrain / exposure features (static priors, refreshed seasonally) ----- #
    elevation_m: Mapped[float] = mapped_column(Float, default=0.0)
    slope_deg: Mapped[float] = mapped_column(Float, default=0.0)
    aspect_deg: Mapped[float] = mapped_column(Float, default=0.0)
    lithology: Mapped[str] = mapped_column(String(24), default=Lithology.LESSER_HIMALAYA.value)
    fault_distance_km: Mapped[float] = mapped_column(Float, default=10.0)
    river_distance_km: Mapped[float] = mapped_column(Float, default=5.0)
    ndvi: Mapped[float] = mapped_column(Float, default=0.5)
    road_distance_km: Mapped[float] = mapped_column(Float, default=1.0)
    historical_events: Mapped[int] = mapped_column(Integer, default=0)

    # people --------------------------------------------------------------- #
    population: Mapped[int] = mapped_column(Integer, default=0)
    households: Mapped[int] = mapped_column(Integer, default=0)
    children: Mapped[int] = mapped_column(Integer, default=0)
    elderly: Mapped[int] = mapped_column(Integer, default=0)
    disabled: Mapped[int] = mapped_column(Integer, default=0)
    registered_phones: Mapped[int] = mapped_column(Integer, default=0)
    schools: Mapped[int] = mapped_column(Integer, default=0)
    health_centres: Mapped[int] = mapped_column(Integer, default=0)

    connectivity: Mapped[str] = mapped_column(String(16), default="mixed")  # good/mixed/poor
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    district: Mapped[District] = relationship(lazy="selectin")


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    hashed_password: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(24), default=Role.CITIZEN.value)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), index=True)
    preferred_lang: Mapped[str] = mapped_column(String(6), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    push_token: Mapped[str | None] = mapped_column(String(160))
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    district: Mapped[District | None] = relationship(lazy="selectin")


# --------------------------------------------------------------------------- #
# Telemetry
# --------------------------------------------------------------------------- #
class RainGauge(Base):
    __tablename__ = "rain_gauges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(90))
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), index=True)
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[str] = mapped_column(String(24), default="rain_gauge")
    status: Mapped[str] = mapped_column(String(16), default="online")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ward: Mapped[Ward | None] = relationship(lazy="selectin")


class TelemetryReading(Base):
    """One row per gauge per observation interval — the raw evidence base."""

    __tablename__ = "telemetry_readings"
    __table_args__ = (
        Index("ix_telemetry_gauge_time", "gauge_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gauge_id: Mapped[int] = mapped_column(ForeignKey("rain_gauges.id"), index=True)
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    rain_1h_mm: Mapped[float] = mapped_column(Float, default=0.0)
    rain_3h_mm: Mapped[float] = mapped_column(Float, default=0.0)
    rain_24h_mm: Mapped[float] = mapped_column(Float, default=0.0)
    rain_72h_mm: Mapped[float] = mapped_column(Float, default=0.0)
    soil_moisture: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1 volumetric proxy
    river_level_m: Mapped[float] = mapped_column(Float, default=0.0)
    forecast_6h_mm: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(32), default="simulated")

    gauge: Mapped[RainGauge] = relationship(lazy="selectin")


class WardRisk(Base):
    """Computed risk per ward per model run. Append-only, so we can replay any day."""

    __tablename__ = "ward_risks"
    __table_args__ = (
        Index("ix_risk_ward_time", "ward_id", "computed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ward_id: Mapped[int] = mapped_column(ForeignKey("wards.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    level: Mapped[str] = mapped_column(String(10), default=RiskLevel.GREEN.value)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    crowd_uplift: Mapped[float] = mapped_column(Float, default=1.0)
    population_at_risk: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(24), default="v1")

    ward: Mapped[Ward] = relationship(lazy="selectin")


class RiskModelConfig(Base):
    """Editable model weights + thresholds.

    Exposing the engine as data (rather than hard-coded constants) is the
    difference between a demo and a deployable system: a district engineer can
    retune after a false-alarm streak and every change is versioned.
    """

    __tablename__ = "risk_model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(24), unique=True)
    weights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- #
# Crowd truth
# --------------------------------------------------------------------------- #
class HazardReport(Base):
    __tablename__ = "hazard_reports"
    __table_args__ = (
        Index("ix_report_ward_status", "ward_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), index=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)

    hazard_type: Mapped[str] = mapped_column(String(32), default="landslide")
    title: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy_m: Mapped[float] = mapped_column(Float, default=0.0)
    photo_path: Mapped[str | None] = mapped_column(String(260))
    self_severity: Mapped[int] = mapped_column(Integer, default=3)  # 1..5

    status: Mapped[str] = mapped_column(String(20), default=ReportStatus.NEW.value, index=True)
    source: Mapped[str] = mapped_column(String(12), default=ReportSource.WEB.value)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    corroborated_by: Mapped[int] = mapped_column(Integer, default=1)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("hazard_reports.id"))

    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    responders_dispatched: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    ward: Mapped[Ward | None] = relationship(lazy="selectin")


# --------------------------------------------------------------------------- #
# Alerts & notifications
# --------------------------------------------------------------------------- #
class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), index=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    hazard_type: Mapped[str] = mapped_column(String(32), default="landslide")
    level: Mapped[str] = mapped_column(String(10), default=RiskLevel.YELLOW.value)
    title: Mapped[str] = mapped_column(String(200), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    localized: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    advice: Mapped[str] = mapped_column(Text, default="")
    auto_issued: Mapped[bool] = mapped_column(Boolean, default=True)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default=AlertStatus.ACTIVE.value, index=True)
    channels: Mapped[list[Any]] = mapped_column(JSON, default=list)
    reach_target: Mapped[int] = mapped_column(Integer, default=0)
    delivered: Mapped[int] = mapped_column(Integer, default=0)
    acknowledged: Mapped[int] = mapped_column(Integer, default=0)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ward: Mapped[Ward | None] = relationship(lazy="selectin")
    district: Mapped[District | None] = relationship(lazy="selectin")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notify_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    channel: Mapped[str] = mapped_column(String(12), default=Channel.SMS.value)
    lang: Mapped[str] = mapped_column(String(6), default="en")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(14), default=NotificationStatus.QUEUED.value)
    provider: Mapped[str] = mapped_column(String(24), default="console")
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- #
# Response assets
# --------------------------------------------------------------------------- #
class Shelter(Base):
    __tablename__ = "shelters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(140))
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), index=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[str] = mapped_column(String(28), default="community_hall")
    capacity: Mapped[int] = mapped_column(Integer, default=100)
    occupied: Mapped[int] = mapped_column(Integer, default=0)
    staff: Mapped[int] = mapped_column(Integer, default=0)
    has_medical: Mapped[bool] = mapped_column(Boolean, default=False)
    has_generator: Mapped[bool] = mapped_column(Boolean, default=False)
    wheelchair_accessible: Mapped[bool] = mapped_column(Boolean, default=False)
    water_security_days: Mapped[int] = mapped_column(Integer, default=1)
    manager_name: Mapped[str] = mapped_column(String(120), default="")
    manager_phone: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(16), default=ShelterStatus.OPEN.value)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    ward: Mapped[Ward | None] = relationship(lazy="selectin")


class RoadSegment(Base):
    __tablename__ = "road_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    from_ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"))
    to_ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"))
    polyline: Mapped[list[Any]] = mapped_column(JSON, default=list)
    length_km: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(14), default=RoadStatus.OPEN.value, index=True)
    is_lifeline: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    clearance_eta_hours: Mapped[float | None] = mapped_column(Float)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    district: Mapped[District | None] = relationship(lazy="selectin")


class ResourceUnit(Base):
    """Deployable assets: NDRF teams, jawas, ambulances, medical camps."""

    __tablename__ = "resource_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(140))
    kind: Mapped[str] = mapped_column(String(32), default="ndrf_team")
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"), index=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    personnel: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="standby")
    eta_hours: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# --------------------------------------------------------------------------- #
# Governance
# --------------------------------------------------------------------------- #
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    actor_label: Mapped[str] = mapped_column(String(140), default="system")
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Subscription(Base):
    """Who wants warnings for which ward, on which channel, in which language."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "ward_id", name="uq_sub_user_ward"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ward_id: Mapped[int] = mapped_column(ForeignKey("wards.id"), index=True)
    channel: Mapped[str] = mapped_column(String(12), default=Channel.SMS.value)
    lang: Mapped[str] = mapped_column(String(6), default="en")
    min_level: Mapped[str] = mapped_column(String(10), default=RiskLevel.YELLOW.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

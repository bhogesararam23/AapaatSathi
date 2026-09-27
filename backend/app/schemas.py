"""Pydantic v2 request/response contracts.

These are the API's public surface, so they double as documentation: every
field the frontend renders is declared here with a type and, where it matters,
a bound. Response models never expose ``hashed_password`` or provider credentials.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

RoleName = Literal["citizen", "field_responder", "district_admin", "system_admin"]
LevelName = Literal["green", "blue", "yellow", "orange", "red"]
LangName = Literal["en", "hi", "gar"]
HazardName = Literal[
    "landslide",
    "flash_flood",
    "road_block",
    "debris_flow",
    "cloudburst",
    "earthquake",
    "glacial_lake",
    "water_logging",
]
RoadState = Literal["open", "caution", "partial", "closed"]
ReportState = Literal["new", "under_review", "confirmed", "dismissed", "resolved"]
ShelterState = Literal["open", "near_full", "overflow", "closed"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=10, max_length=15)
    password: str = Field(min_length=8, max_length=128)
    preferred_lang: LangName = "en"
    role: RoleName = "citizen"
    ward_code: str | None = None
    district_code: str | None = None

    @field_validator("phone")
    @classmethod
    def _digits(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = "".join(c for c in v if c.isdigit() or c == "+")
        if len(cleaned.lstrip("+")) < 10:
            raise ValueError("phone needs at least 10 digits")
        return cleaned


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=160, description="email or phone")
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class UserOut(ORMModel):
    id: int
    full_name: str
    email: str | None = None
    phone: str | None = None
    role: RoleName
    preferred_lang: str
    is_active: bool
    is_verified: bool
    trust_score: float
    district_id: int | None = None
    ward_id: int | None = None
    created_at: datetime


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    preferred_lang: LangName | None = None
    phone: str | None = None
    ward_code: str | None = None
    push_token: str | None = None


# --------------------------------------------------------------------------- #
# geography
# --------------------------------------------------------------------------- #
class DistrictOut(ORMModel):
    id: int
    code: str
    name: str
    name_hi: str = ""
    state: str
    headquarters: str
    latitude: float
    longitude: float
    area_km2: float
    population: int
    control_room: str


class WardBrief(ORMModel):
    id: int
    code: str
    name: str
    name_hi: str = ""
    district_id: int
    latitude: float
    longitude: float


class WardOut(ORMModel):
    id: int
    code: str
    name: str
    name_hi: str = ""
    district_id: int
    latitude: float
    longitude: float
    polygon: list[Any] = []
    elevation_m: float
    slope_deg: float
    aspect_deg: float
    lithology: str
    fault_distance_km: float
    river_distance_km: float
    ndvi: float
    road_distance_km: float
    historical_events: int
    population: int
    households: int
    children: int
    elderly: int
    disabled: int
    registered_phones: int
    schools: int
    health_centres: int
    connectivity: str
    notes: str = ""


class WardWithRisk(WardOut):
    district_name: str | None = None
    risk: "RiskOut | None" = None


# --------------------------------------------------------------------------- #
# risk
# --------------------------------------------------------------------------- #
class FactorOut(BaseModel):
    key: str
    label: str
    unit: str
    observed: float
    normalised: float
    weight: float
    contribution: float
    rationale: str


class RiskOut(ORMModel):
    ward_id: int
    computed_at: datetime
    score: float
    level: LevelName
    confidence: float
    crowd_uplift: float
    population_at_risk: int
    model_version: str
    factors: dict[str, Any] = {}


class RiskDetail(RiskOut):
    ward_code: str = ""
    ward_name: str = ""
    district_name: str = ""
    population: int = 0
    probability_24h: float = 0.0
    factor_list: list[FactorOut] = []
    gauge_source: str = "simulated"
    open_reports: int = 0
    confirmed_reports: int = 0


class ModelInfoOut(BaseModel):
    version: str
    weights: dict[str, float]
    thresholds: dict[str, float]
    weights_sum: float
    factor_docs: list[dict[str, Any]]
    crowd_uplift_cap: float
    active_config: str | None = None
    disclaimer: str


class RiskSeriesOut(BaseModel):
    ward_code: str
    series: list[dict[str, Any]]
    score_history: list[dict[str, Any]]


# --------------------------------------------------------------------------- #
# alerts
# --------------------------------------------------------------------------- #
class AlertOut(ORMModel):
    id: int
    code: str
    ward_id: int | None = None
    district_id: int | None = None
    hazard_type: str
    level: LevelName
    title: str
    message: str
    localized: dict[str, Any] = {}
    score: float
    advice: str
    auto_issued: bool
    status: str
    channels: list[str] = []
    reach_target: int
    delivered: int
    acknowledged: int
    issued_at: datetime
    expires_at: datetime | None = None
    #: Outcome of the most recent dispatch attempt, e.g. {"simulated": 120} or
    #: {"suppressed": 60}. Without this a client cannot tell a deliberately
    #: deduplicated duplicate broadcast from a delivery that silently failed.
    reach: dict[str, int] = {}


class AlertCreateIn(BaseModel):
    ward_code: str | None = None
    district_code: str | None = None
    hazard_type: HazardName = "landslide"
    level: LevelName = "yellow"
    title: str | None = Field(default=None, max_length=200)
    message: str | None = None
    channels: list[Literal["sms", "ivr", "push", "inapp"]] = ["sms", "ivr"]
    ttl_minutes: int = Field(default=240, ge=5, le=24 * 60)
    broadcast: bool = True

    @model_validator(mode="after")
    def _need_target(self) -> "AlertCreateIn":
        if not self.ward_code and not self.district_code:
            raise ValueError("provide ward_code or district_code")
        return self


class AlertStatusIn(BaseModel):
    status: Literal["active", "acknowledged", "expired", "revoked"]


# --------------------------------------------------------------------------- #
# crowd reports
# --------------------------------------------------------------------------- #
class ReportCreateIn(BaseModel):
    hazard_type: HazardName = "landslide"
    title: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=2000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(default=0.0, ge=0, le=10_000)
    self_severity: int = Field(default=3, ge=1, le=5)
    ward_code: str | None = None
    lang: LangName = "en"
    consent_media: bool = False


class ReportOut(ORMModel):
    id: int
    code: str
    ward_id: int | None = None
    district_id: int | None = None
    hazard_type: str
    title: str
    description: str
    latitude: float
    longitude: float
    accuracy_m: float
    self_severity: int
    status: str
    source: str
    confidence: float
    corroborated_by: int
    responders_dispatched: int
    photo_url: str | None = None
    ward_name: str | None = None
    district_name: str | None = None
    reporter_alias: str | None = None
    created_at: datetime
    verified_at: datetime | None = None
    resolution_note: str = ""


class ReportVerdictIn(BaseModel):
    status: ReportState
    note: str = Field(default="", max_length=1000)


class ReportNearbyIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=1.5, gt=0, le=25)


# --------------------------------------------------------------------------- #
# response assets
# --------------------------------------------------------------------------- #
class ShelterOut(ORMModel):
    id: int
    code: str
    name: str
    ward_id: int | None = None
    ward_name: str | None = None
    latitude: float
    longitude: float
    kind: str
    capacity: int
    occupied: int
    staff: int
    has_medical: bool
    has_generator: bool
    wheelchair_accessible: bool
    water_security_days: int
    manager_name: str
    manager_phone: str
    status: str
    free_places: int = 0
    distance_km: float | None = None
    last_updated_at: datetime


class ShelterUpdateIn(BaseModel):
    occupied: int | None = Field(default=None, ge=0)
    staff: int | None = Field(default=None, ge=0)
    capacity: int | None = Field(default=None, ge=0)
    status: ShelterState | None = None
    water_security_days: int | None = Field(default=None, ge=0, le=60)
    note: str | None = Field(default=None, max_length=500)


class ShelterCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    ward_code: str
    kind: str = "community_hall"
    capacity: int = Field(default=100, ge=1, le=20_000)
    latitude: float = Field(default=0.0, ge=-90, le=90)
    longitude: float = Field(default=0.0, ge=-180, le=180)
    has_medical: bool = False
    has_generator: bool = False
    wheelchair_accessible: bool = False
    manager_name: str = ""
    manager_phone: str = ""


class RoadOut(ORMModel):
    id: int
    code: str
    name: str
    district_id: int | None = None
    district_name: str | None = None
    from_ward_id: int | None = None
    to_ward_id: int | None = None
    from_ward_name: str | None = None
    to_ward_name: str | None = None
    polyline: list[Any] = []
    length_km: float
    status: str
    is_lifeline: bool
    note: str
    clearance_eta_hours: float | None = None
    updated_at: datetime


class RoadUpdateIn(BaseModel):
    status: RoadState
    note: str = Field(default="", max_length=500)
    clearance_eta_hours: float | None = Field(default=None, ge=0, le=500)


class ResourceOut(ORMModel):
    id: int
    code: str
    name: str
    kind: str
    ward_id: int | None = None
    ward_name: str | None = None
    latitude: float
    longitude: float
    personnel: int
    status: str
    eta_hours: float | None = None
    note: str
    updated_at: datetime


# --------------------------------------------------------------------------- #
# notifications / audit / analytics
# --------------------------------------------------------------------------- #
class NotificationOut(ORMModel):
    id: int
    alert_id: int | None = None
    phone: str | None = None
    channel: str
    lang: str
    body: str
    status: str
    provider: str
    provider_ref: str | None = None
    error: str | None = None
    attempts: int
    created_at: datetime
    sent_at: datetime | None = None


class NotificationStatsOut(BaseModel):
    provider: str
    simulated: bool
    by_status: dict[str, int]
    by_channel: dict[str, int]
    by_lang: dict[str, int]
    total: int
    reach_target: int
    note: str


class AuditOut(ORMModel):
    id: int
    actor_label: str
    action: str
    entity: str
    entity_id: str
    detail: dict[str, Any] = {}
    created_at: datetime


class AnalyticsOut(BaseModel):
    wards: int
    districts: int
    population_covered: int
    phones_reachable: int
    alerts_24h: int
    reports_24h: int
    reports_verified_24h: int
    open_reports: int
    shelters: int
    shelter_capacity: int
    shelter_occupied: int
    roads_closed: int
    roads_total: int
    levels: dict[str, int]
    population_exposed: int
    mean_confidence: float
    median_lead_minutes: float | None = None
    telemetry_source: str
    generated_at: datetime


class ScenarioIn(BaseModel):
    ward_code: str
    rain_1h_mm: float = Field(ge=0, le=500)
    rain_24h_mm: float = Field(ge=0, le=1200)
    rain_72h_mm: float = Field(ge=0, le=2500)
    forecast_6h_mm: float = Field(ge=0, le=600)
    soil_moisture: float = Field(ge=0, le=1)
    broadcast: bool = False

    @model_validator(mode="after")
    def _ordering(self) -> "ScenarioIn":
        if self.rain_1h_mm > self.rain_24h_mm > 0:
            raise ValueError("rain_1h_mm cannot exceed rain_24h_mm")
        if self.rain_24h_mm > self.rain_72h_mm > 0:
            raise ValueError("rain_24h_mm cannot exceed rain_72h_mm")
        return self


class SweepOut(BaseModel):
    evaluated: int
    created: int
    suppressed: int
    escalated: list[dict[str, Any]]
    telemetry: dict[str, Any] = {}


class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    notifications: str
    simulated_delivery: bool
    seed_present: bool
    time: datetime


class MessageOut(BaseModel):
    message: str
    detail: Any | None = None


TokenOut.model_rebuild()
RiskOut.model_rebuild()
WardWithRisk.model_rebuild()

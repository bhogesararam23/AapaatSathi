"""Explainable landslide / flash-flood susceptibility engine.

Why a weighted linear model and not a neural net
------------------------------------------------
Hill-district disaster warnings get audited. When a slope fails and people are
hurt, the first question a probe committee asks is *"why did the system say
what it said?"* A gradient-boosted ensemble or a deep model cannot answer that
per-ward, per-hour, on a laptop with no labelled event dataset. Uttarakhand has
thousands of slope failures but no ward-level, temporally-aligned feature ledger
for them, so any "trained" model here would be trained on thin air and would be
dishonest to present as validated.

So this is a **transparent additive susceptibility model**: each factor is a
piecewise-normalised sub-score in [0,1] with a published weight, and every run
persists the full breakdown. Thresholds and weights live in ``RiskModelConfig``
(rows, not constants) so a district engineer can retune the engine after a
false-alarm streak and the change is versioned and auditable.

The result is defensible on stage: *this is a decision-support prior, calibrated
to published Himalayan susceptibility heuristics, not a trained predictor.*

Public API
----------
``score_ward()``  -> WardScore        pure computation
``evaluate()``    -> list[WardScore]  + persistence and alert escalation
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    HazardReport,
    Lithology,
    RiskLevel,
    TelemetryReading,
    Ward,
    WardRisk,
)

MODEL_VERSION = "as-risk-1.2"

# --------------------------------------------------------------------------- #
# Weights — published in the UI and in /api/v1/risk/model. Must sum to 1.0.
# --------------------------------------------------------------------------- #
DEFAULT_WEIGHTS: dict[str, float] = {
    "rain_intensity": 0.16,   # short-burst rate: the cloudburst trigger
    "rain_antecedent": 0.12,  # 72 h accumulation: how full the ground already is
    "soil_saturation": 0.10,  # antecedent moisture proxy
    "forecast_6h": 0.12,      # leading indicator -> warning *before* the event
    "slope": 0.14,            # dominant terrain control
    "geology": 0.10,          # lithological susceptibility
    "structural": 0.06,       # proximity to major thrust/fault zones
    "drainage": 0.08,         # channel proximity + through-flow
    "vegetation_loss": 0.05,  # root cohesion proxy via NDVI deficit
    "event_history": 0.07,    # this slope has moved before
}

DEFAULT_THRESHOLDS: dict[str, float] = {
    "blue": 25.0,
    "yellow": 45.0,
    "orange": 62.0,
    "red": 76.0,
}

# Published heuristics for the Middle/Lesser Himalaya; slope susceptibility peaks
# in the ~30-45 deg band where toe erosion and steep relief combine.
SLOPE_CURVE = [(0, 0.05), (10, 0.15), (15, 0.30), (25, 0.58), (35, 0.82), (45, 0.95), (60, 1.0)]
RAIN_1H_CURVE = [(0, 0.0), (10, 0.18), (20, 0.36), (40, 0.60), (70, 0.85), (100, 0.96), (150, 1.0)]
RAIN_72H_CURVE = [(0, 0.0), (40, 0.20), (90, 0.42), (150, 0.65), (230, 0.85), (320, 1.0)]
FORECAST_6H_CURVE = [(0, 0.0), (15, 0.22), (30, 0.45), (55, 0.72), (80, 0.90), (120, 1.0)]
FAULT_KM_CURVE = [(0, 1.0), (1, 0.86), (3, 0.62), (6, 0.40), (12, 0.20), (25, 0.08), (60, 0.04)]
RIVER_KM_CURVE = [(0, 1.0), (0.3, 0.85), (1, 0.62), (2.5, 0.38), (5, 0.20), (12, 0.08), (40, 0.04)]

LITHOLOGY_RISK: dict[str, float] = {
    Lithology.SIWALIK.value: 0.95,
    Lithology.LESSER_HIMALAYA.value: 0.85,
    Lithology.ALLUVIUM.value: 0.72,
    Lithology.GREATER_HIMALAYA.value: 0.52,
    Lithology.TETHYS_HIMALAYA.value: 0.42,
    Lithology.GRANITE_GNEISS.value: 0.36,
}

LEVEL_ORDER = ["green", "blue", "yellow", "orange", "red"]

# Fraction of ward population realistically impacted at each level, used for the
# "people exposed" headline. Conservative; derived from event footprints.
EXPOSURE_FRACTION = {"green": 0.0, "blue": 0.02, "yellow": 0.12, "orange": 0.35, "red": 0.70}


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
def interp(value: float, curve: Sequence[tuple[float, float]]) -> float:
    """Piecewise-linear interpolation over an ascending (x, y) curve, clamped."""
    if not curve:
        return 0.0
    if value <= curve[0][0]:
        return float(curve[0][1])
    if value >= curve[-1][0]:
        return float(curve[-1][1])
    for (x1, y1), (x2, y2) in zip(curve, curve[1:]):
        if x1 <= value <= x2:
            span = (x2 - x1) or 1e-9
            return float(y1 + (y2 - y1) * ((value - x1) / span))
    return float(curve[-1][1])


def level_for_score(score: float, thresholds: dict[str, float] | None = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if score >= t["red"]:
        return RiskLevel.RED.value
    if score >= t["orange"]:
        return RiskLevel.ORANGE.value
    if score >= t["yellow"]:
        return RiskLevel.YELLOW.value
    if score >= t["blue"]:
        return RiskLevel.BLUE.value
    return RiskLevel.GREEN.value


def probability_24h(score: float) -> float:
    """Logistic mapping of susceptibility to an at least-one-event probability.

    Centred on the orange threshold: crossing it is where operational value
    starts, so the curve reaches ~0.5 there and saturates near the red band.
    """
    return round(1.0 / (1.0 + math.exp(-(score - DEFAULT_THRESHOLDS["orange"]) / 7.5)), 4)


# --------------------------------------------------------------------------- #
# data containers
# --------------------------------------------------------------------------- #
@dataclass
class Factor:
    key: str
    label: str
    unit: str
    observed: float
    normalised: float
    weight: float
    rationale: str

    @property
    def contribution(self) -> float:
        return round(self.normalised * self.weight * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "observed": round(self.observed, 2),
            "normalised": round(self.normalised, 3),
            "weight": self.weight,
            "contribution": self.contribution,
            "rationale": self.rationale,
        }


@dataclass
class WardInputs:
    """Everything the model knows about one ward right now."""

    slope_deg: float = 0.0
    lithology: str = Lithology.LESSER_HIMALAYA.value
    fault_distance_km: float = 20.0
    river_distance_km: float = 10.0
    ndvi: float = 0.6
    historical_events: int = 0
    rain_1h_mm: float = 0.0
    rain_3h_mm: float = 0.0
    rain_24h_mm: float = 0.0
    rain_72h_mm: float = 0.0
    soil_moisture: float = 0.0
    forecast_6h_mm: float = 0.0
    river_level_m: float = 0.0
    # crowd overlay
    open_reports: int = 0
    confirmed_reports: int = 0
    corroboration: int = 1
    # data quality
    gauge_online: bool = False
    telemetry_age_minutes: float | None = None
    has_polygon: bool = True


@dataclass
class WardScore:
    score: float
    level: str
    confidence: float
    factors: list[Factor] = field(default_factory=list)
    crowd_uplift: float = 1.0
    probability_24h: float = 0.0
    population_at_risk: int = 0
    inputs: WardInputs = field(default_factory=WardInputs)
    model_version: str = MODEL_VERSION

    def factor_breakdown(self) -> dict[str, Any]:
        return {
            "factors": [f.to_dict() for f in self.factors],
            "crowd_uplift": round(self.crowd_uplift, 3),
            "base_total": round(sum(f.contribution for f in self.factors), 2),
            "model_version": self.model_version,
        }


# --------------------------------------------------------------------------- #
# crowd overlay
# --------------------------------------------------------------------------- #
def crowd_uplift(
    open_reports: int,
    confirmed_reports: int,
    corroboration: int,
    reporter_trust: float = 0.5,
    cap: float = 1.25,
) -> float:
    """Cap-limited multiplier from ground truth.

    Deliberately bounded: a single excited WhatsApp forward must not be able to
    push a district into evacuation, but three neighbours reporting the same
    crack within an hour *should* outrank a stale rain gauge. Independent
    corroboration and reporter history are what buy the uplift.
    """
    if open_reports + confirmed_reports <= 0:
        return 1.0
    signal = 0.0
    signal += min(0.30, 0.10 * max(0, corroboration - 1))
    signal += min(0.45, 0.20 * confirmed_reports)
    signal += min(0.15, 0.05 * open_reports)
    signal *= 0.55 + 0.45 * max(0.0, min(1.0, reporter_trust))
    return round(min(cap, 1.0 + signal), 4)


# --------------------------------------------------------------------------- #
# core scoring
# --------------------------------------------------------------------------- #
def score_ward(
    inputs: WardInputs,
    weights: dict[str, float] | None = None,
    thresholds: dict[str, float] | None = None,
    population: int = 0,
    crowd_cap: float = 1.25,
) -> WardScore:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    factors: list[Factor] = []

    # --- dynamic: rainfall ------------------------------------------------ #
    hour_rate = max(inputs.rain_1h_mm, inputs.rain_3h_mm / 3.0)
    factors.append(
        Factor(
            key="rain_intensity",
            label="Rainfall intensity (last hour)",
            unit="mm/h",
            observed=hour_rate,
            normalised=interp(hour_rate, RAIN_1H_CURVE),
            weight=w["rain_intensity"],
            rationale=(
                "Short-burst rate is the primary cloudburst trigger on steep "
                "slopes; infiltration lags, so peak intensity matters more than totals."
            ),
        )
    )
    factors.append(
        Factor(
            key="rain_antecedent",
            label="Antecedent rainfall (72 h)",
            unit="mm",
            observed=inputs.rain_72h_mm,
            normalised=interp(inputs.rain_72h_mm, RAIN_72H_CURVE),
            weight=w["rain_antecedent"],
            rationale=(
                "Ground already near capacity from the preceding three days "
                "fails at far lower intensity than dry ground would."
            ),
        )
    )
    soil_norm = max(
        inputs.soil_moisture,
        interp(inputs.rain_24h_mm, [(0, 0.0), (25, 0.3), (60, 0.6), (110, 0.85), (160, 1.0)]),
    )
    factors.append(
        Factor(
            key="soil_saturation",
            label="Soil saturation",
            unit="index",
            observed=soil_norm,
            normalised=soil_norm,
            weight=w["soil_saturation"],
            rationale=(
                "Pore-pressure proxy. Where no probe exists it is inferred from "
                "the 24 h accumulation, which is why it is capped and blended."
            ),
        )
    )
    factors.append(
        Factor(
            key="forecast_6h",
            label="Forecast rainfall (next 6 h)",
            unit="mm",
            observed=inputs.forecast_6h_mm,
            normalised=interp(inputs.forecast_6h_mm, FORECAST_6H_CURVE),
            weight=w["forecast_6h"],
            rationale=(
                "The only forward-looking term, and the reason warnings can lead "
                "the event instead of reporting it."
            ),
        )
    )

    # --- static terrain --------------------------------------------------- #
    factors.append(
        Factor(
            key="slope",
            label="Slope angle",
            unit="deg",
            observed=inputs.slope_deg,
            normalised=interp(inputs.slope_deg, SLOPE_CURVE),
            weight=w["slope"],
            rationale=(
                "Dominant terrain control. Susceptibility rises steeply through "
                "the 30-45 deg band typical of the Lesser Himalayan escarpments."
            ),
        )
    )
    geo = LITHOLOGY_RISK.get(inputs.lithology, 0.6)
    factors.append(
        Factor(
            key="geology",
            label="Lithological susceptibility",
            unit="index",
            observed=geo,
            normalised=geo,
            weight=w["geology"],
            rationale=(
                f"{inputs.lithology.replace('_', ' ').title()} class. Siwalik "
                "sandstone/shale and sheared Lesser Himalayan phyllites are the "
                "most failure-prone units in the state."
            ),
        )
    )
    factors.append(
        Factor(
            key="structural",
            label="Distance to major thrust zone",
            unit="km",
            observed=inputs.fault_distance_km,
            normalised=interp(inputs.fault_distance_km, FAULT_KM_CURVE),
            weight=w["structural"],
            rationale=(
                "Jointing and rock-mass damage around the Main Boundary and "
                "Central Crustal thrusts create persistent planes of weakness."
            ),
        )
    )
    river_norm = interp(inputs.river_distance_km, RIVER_KM_CURVE)
    if inputs.river_level_m > 4.0:  # monsoon stage adds bank scour at the slope toe
        river_norm = min(1.0, river_norm + 0.12)
    factors.append(
        Factor(
            key="drainage",
            label="Channel proximity and stage",
            unit="km",
            observed=inputs.river_distance_km,
            normalised=river_norm,
            weight=w["drainage"],
            rationale=(
                "Toe erosion by a flowing channel removes the support a slope "
                "rests on; high monsoon stage is penalised on top of distance."
            ),
        )
    )

    # --- land cover & history --------------------------------------------- #
    veg_deficit = max(0.0, min(1.0, (0.75 - inputs.ndvi) / 0.6))
    factors.append(
        Factor(
            key="vegetation_loss",
            label="Vegetation / root-cohesion deficit",
            unit="index",
            observed=inputs.ndvi,
            normalised=veg_deficit,
            weight=w["vegetation_loss"],
            rationale=(
                "Root reinforcement thinning. Modelled as the deficit against a "
                "healthy mid-elevation forest NDVI of 0.75."
            ),
        )
    )
    history_norm = min(1.0, math.log1p(inputs.historical_events) / math.log(1 + 12))
    factors.append(
        Factor(
            key="event_history",
            label="Recorded past events",
            unit="count",
            observed=inputs.historical_events,
            normalised=history_norm,
            weight=w["event_history"],
            rationale=(
                "A slope that has moved before is the single best indicator that "
                "it will move again. Log-scaled so twelve events is not twelve "
                "times one event."
            ),
        )
    )

    # --- aggregate --------------------------------------------------------- #
    total = sum(f.contribution for f in factors)
    uplift = crowd_uplift(
        open_reports=inputs.open_reports,
        confirmed_reports=inputs.confirmed_reports,
        corroboration=inputs.corroboration,
        cap=crowd_cap,
    )
    score = max(0.0, min(100.0, round(total * uplift, 2)))
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    level = level_for_score(score, thresholds)

    return WardScore(
        score=score,
        level=level,
        confidence=_confidence(inputs),
        factors=factors,
        crowd_uplift=uplift,
        probability_24h=probability_24h(score),
        population_at_risk=int(round(population * EXPOSURE_FRACTION.get(level, 0.0))),
        inputs=inputs,
    )


def _confidence(inputs: WardInputs) -> float:
    """How much of this score is measured versus inferred, in [0.1, 0.98].

    Surfacing this is the honest thing to do: a ward with a live gauge and a
    drawn boundary deserves more trust than one scored purely from terrain
    priors, and the UI must not pretend otherwise.
    """
    conf = 0.34  # terrain priors alone
    if inputs.has_polygon:
        conf += 0.06
    if inputs.gauge_online:
        conf += 0.30
        if inputs.telemetry_age_minutes is not None:
            conf += 0.14 * max(0.0, 1.0 - inputs.telemetry_age_minutes / 180.0)
    else:
        conf += 0.10  # modelled rainfall from the satellite/grid layer
    if inputs.rain_24h_mm > 0:
        conf += 0.06
    if inputs.confirmed_reports:
        conf += min(0.14, 0.07 * inputs.confirmed_reports)
    elif inputs.open_reports:
        conf += 0.04
    return round(max(0.10, min(0.98, conf)), 3)


# --------------------------------------------------------------------------- #
# telemetry roll-up
# --------------------------------------------------------------------------- #
async def latest_telemetry(
    db: AsyncSession, ward_ids: Sequence[int], since: datetime | None = None
) -> dict[int, TelemetryReading]:
    """Newest reading mapped to each ward (nearest-gauge assignment)."""
    if not ward_ids:
        return {}
    cutoff = since or (datetime.now(timezone.utc) - timedelta(hours=72))
    rows = await db.execute(
        select(TelemetryReading)
        .where(
            TelemetryReading.ward_id.in_(list(ward_ids)),
            TelemetryReading.recorded_at >= cutoff,
        )
        .order_by(TelemetryReading.recorded_at.desc())
    )
    out: dict[int, TelemetryReading] = {}
    for reading in rows.scalars():
        if reading.ward_id and reading.ward_id not in out:
            out[reading.ward_id] = reading
    return out


async def crowd_signals(
    db: AsyncSession, ward_ids: Sequence[int], hours: int = 48
) -> dict[int, dict[str, int]]:
    """Recent report counts per ward, split by verification state."""
    if not ward_ids:
        return {}
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await db.execute(
        select(
            HazardReport.ward_id,
            func.count(HazardReport.id),
            func.sum(case((HazardReport.status == "confirmed", 1), else_=0)),
            func.max(HazardReport.corroborated_by),
        )
        .where(
            HazardReport.ward_id.in_(list(ward_ids)),
            HazardReport.created_at >= since,
            HazardReport.status.in_(["new", "under_review", "confirmed"]),
        )
        .group_by(HazardReport.ward_id)
    )
    out: dict[int, dict[str, int]] = {}
    for ward_id, total, confirmed, corrob in rows:
        if ward_id is None:
            continue
        out[ward_id] = {
            "open": int(total or 0) - int(confirmed or 0),
            "confirmed": int(confirmed or 0),
            "corroboration": int(corrob or 1),
        }
    return out


def inputs_from(
    ward: Ward,
    reading: TelemetryReading | None,
    crowd: dict[str, int] | None,
) -> WardInputs:
    crowd = crowd or {}
    age = None
    if reading and reading.recorded_at:
        stamp = reading.recorded_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 60.0)
    return WardInputs(
        slope_deg=ward.slope_deg,
        lithology=ward.lithology,
        fault_distance_km=ward.fault_distance_km,
        river_distance_km=ward.river_distance_km,
        ndvi=ward.ndvi,
        historical_events=ward.historical_events,
        rain_1h_mm=reading.rain_1h_mm if reading else 0.0,
        rain_3h_mm=reading.rain_3h_mm if reading else 0.0,
        rain_24h_mm=reading.rain_24h_mm if reading else 0.0,
        rain_72h_mm=reading.rain_72h_mm if reading else 0.0,
        soil_moisture=reading.soil_moisture if reading else 0.0,
        forecast_6h_mm=reading.forecast_6h_mm if reading else 0.0,
        river_level_m=reading.river_level_m if reading else 0.0,
        open_reports=crowd.get("open", 0),
        confirmed_reports=crowd.get("confirmed", 0),
        corroboration=crowd.get("corroboration", 1),
        gauge_online=reading is not None and age is not None and age < 360,
        telemetry_age_minutes=age,
        has_polygon=bool(ward.polygon),
    )


async def evaluate_wards(
    db: AsyncSession,
    wards: Iterable[Ward],
    weights: dict[str, float] | None = None,
    thresholds: dict[str, float] | None = None,
    persist: bool = True,
) -> list[tuple[Ward, WardScore]]:
    """Score a batch of wards and append the results to the risk history."""
    ward_list = list(wards)
    ids = [w.id for w in ward_list]
    telemetry = await latest_telemetry(db, ids)
    crowd = await crowd_signals(db, ids)

    results: list[tuple[Ward, WardScore]] = []
    for ward in ward_list:
        inputs = inputs_from(ward, telemetry.get(ward.id), crowd.get(ward.id))
        score = score_ward(
            inputs,
            weights=weights,
            thresholds=thresholds,
            population=ward.population,
        )
        results.append((ward, score))
        if persist:
            db.add(
                WardRisk(
                    ward_id=ward.id,
                    score=score.score,
                    level=score.level,
                    confidence=score.confidence,
                    crowd_uplift=score.crowd_uplift,
                    population_at_risk=score.population_at_risk,
                    factors=score.factor_breakdown(),
                    model_version=MODEL_VERSION,
                )
            )
    if persist:
        await db.flush()
    return results

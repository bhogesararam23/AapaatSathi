"""Tests for the explainable susceptibility engine.

This is the module the whole product rests on, so the properties under test are
the ones a reviewer would actually challenge: do the weights add up, does the
interpolation stay inside its documented bounds, does a wet steep Siwalik ward
outrank a dry flat one, can a crowd rumour cap-size its way into an evacuation
order, and does the system admit when it is guessing (``confidence``)?
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from sqlalchemy import func, select

from app.models import Ward, WardRisk
from app.services.risk_engine import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    EXPOSURE_FRACTION,
    LEVEL_ORDER,
    SLOPE_CURVE,
    MODEL_VERSION,
    WardInputs,
    _confidence,
    crowd_uplift,
    interp,
    level_for_score,
    probability_24h,
    score_ward,
)

# --------------------------------------------------------------------------- #
# reference inputs: a genuinely quiet ward and a textbook monsoon slope
# --------------------------------------------------------------------------- #
QUIET = WardInputs(
    slope_deg=3.0,
    lithology="granite_gneiss",
    fault_distance_km=45.0,
    river_distance_km=35.0,
    ndvi=0.79,
    historical_events=0,
    rain_1h_mm=0.0,
    rain_3h_mm=0.0,
    rain_24h_mm=0.0,
    rain_72h_mm=0.0,
    soil_moisture=0.0,
    forecast_6h_mm=0.0,
    river_level_m=0.6,
)

WET_STEEP_SIWALIK = WardInputs(
    slope_deg=38.0,
    lithology="siwalik",
    fault_distance_km=1.2,
    river_distance_km=0.4,
    ndvi=0.34,
    historical_events=9,
    rain_1h_mm=62.0,
    rain_3h_mm=150.0,
    rain_24h_mm=210.0,
    rain_72h_mm=285.0,
    soil_moisture=0.86,
    forecast_6h_mm=72.0,
    river_level_m=5.2,
    gauge_online=True,
    telemetry_age_minutes=6.0,
)

ABSURD = WardInputs(
    slope_deg=90.0,
    lithology="siwalik",
    fault_distance_km=0.0,
    river_distance_km=0.0,
    ndvi=0.0,
    historical_events=999,
    rain_1h_mm=400.0,
    rain_3h_mm=900.0,
    rain_24h_mm=900.0,
    rain_72h_mm=2000.0,
    soil_moisture=1.0,
    forecast_6h_mm=500.0,
    river_level_m=30.0,
    open_reports=99,
    confirmed_reports=99,
    corroboration=99,
    gauge_online=True,
    telemetry_age_minutes=0.0,
)


# --------------------------------------------------------------------------- #
# published weights
# --------------------------------------------------------------------------- #
def test_published_weights_sum_to_one():
    assert len(DEFAULT_WEIGHTS) == 10
    assert round(sum(DEFAULT_WEIGHTS.values()), 9) == 1.0
    assert all(0.0 < w < 1.0 for w in DEFAULT_WEIGHTS.values())


def test_thresholds_are_ascending_and_named_as_documented():
    levels = ["blue", "yellow", "orange", "red"]
    values = [DEFAULT_THRESHOLDS[lv] for lv in levels]
    assert values == sorted(values)
    assert values == [25.0, 45.0, 62.0, 76.0]


# --------------------------------------------------------------------------- #
# interp
# --------------------------------------------------------------------------- #
def test_interp_clamps_below_and_above_the_curve():
    assert interp(-1000, SLOPE_CURVE) == SLOPE_CURVE[0][1]
    assert interp(0, SLOPE_CURVE) == SLOPE_CURVE[0][1]
    assert interp(1000, SLOPE_CURVE) == SLOPE_CURVE[-1][1]
    assert interp(60, SLOPE_CURVE) == SLOPE_CURVE[-1][1]


def test_interp_hits_the_knots_exactly():
    for x, y in SLOPE_CURVE:
        assert interp(x, SLOPE_CURVE) == pytest.approx(y)


def test_interp_is_linear_between_knots():
    # (15, 0.30) -> (25, 0.58): 20 is exactly halfway.
    assert interp(20, SLOPE_CURVE) == pytest.approx(0.44)
    assert interp(17.5, SLOPE_CURVE) == pytest.approx(0.30 + 0.28 * 0.25)
    assert interp(22.5, SLOPE_CURVE) == pytest.approx(0.30 + 0.28 * 0.75)


def test_interp_of_an_empty_curve_is_zero():
    assert interp(42.0, []) == 0.0


def test_interp_is_monotonic_on_every_ascending_curve():
    from app.services import risk_engine as re

    curves = [
        re.RAIN_1H_CURVE,
        re.RAIN_72H_CURVE,
        re.FORECAST_6H_CURVE,
        SLOPE_CURVE,
    ]
    for curve in curves:
        xs = [curve[0][0] - 5 + i * 0.7 for i in range(int(curve[-1][0] / 0.7) + 8)]
        ys = [interp(x, curve) for x in xs]
        assert ys == sorted(ys), f"{curve} interpolation is not monotonic"
        assert all(0.0 <= y <= 1.0 for y in ys)


def test_distance_curves_are_decreasing_near_the_source():
    """Faults and channels are riskier *closer*, so those curves invert."""
    from app.services.risk_engine import FAULT_KM_CURVE, RIVER_KM_CURVE

    assert interp(0, FAULT_KM_CURVE) > interp(12, FAULT_KM_CURVE) > interp(60, FAULT_KM_CURVE)
    assert interp(0, RIVER_KM_CURVE) > interp(5, RIVER_KM_CURVE) > interp(40, RIVER_KM_CURVE)


# --------------------------------------------------------------------------- #
# end-to-end scoring behaviour
# --------------------------------------------------------------------------- #
def test_quiet_ward_scores_far_below_a_wet_steep_siwalik_ward():
    quiet = score_ward(QUIET)
    severe = score_ward(WET_STEEP_SIWALIK)

    assert quiet.score < 15.0
    assert severe.score > 65.0
    assert severe.score - quiet.score > 50.0
    assert quiet.level == "green"
    assert LEVEL_ORDER.index(severe.level) >= LEVEL_ORDER.index("orange")


def test_score_is_the_weighted_sum_of_its_factors_when_the_crowd_is_silent():
    result = score_ward(WET_STEEP_SIWALIK)
    assert result.crowd_uplift == 1.0
    assert result.score == pytest.approx(sum(f.contribution for f in result.factors), abs=0.02)
    breakdown = result.factor_breakdown()
    assert breakdown["base_total"] == pytest.approx(result.score, abs=0.05)
    assert breakdown["model_version"] == MODEL_VERSION


def test_score_stays_inside_zero_and_hundred_even_when_saturated():
    result = score_ward(ABSURD)
    assert 0.0 <= result.score <= 100.0
    assert result.score == 100.0
    assert result.level == "red"
    zero = score_ward(WardInputs(lithology="granite_gneiss", ndvi=1.0))
    assert 0.0 <= zero.score <= 100.0
    assert zero.level == "green"


@pytest.mark.parametrize(
    "score, expected",
    [
        (0.0, "green"),
        (24.99, "green"),
        (25.0, "blue"),
        (44.99, "blue"),
        (45.0, "yellow"),
        (61.99, "yellow"),
        (62.0, "orange"),
        (75.99, "orange"),
        (76.0, "red"),
        (100.0, "red"),
    ],
)
def test_level_thresholds_map_at_the_documented_cut_offs(score, expected):
    assert level_for_score(score) == expected


def test_level_mapping_is_monotonic_in_the_score():
    indices = [LEVEL_ORDER.index(level_for_score(s)) for s in range(0, 101)]
    assert indices == sorted(indices)


def test_level_thresholds_can_be_retuned_per_district():
    looser = {"blue": 5.0, "yellow": 10.0, "orange": 15.0, "red": 20.0}
    assert level_for_score(12.0, looser) == "yellow"
    assert level_for_score(12.0) == "green"
    # partial overrides fall back to the published defaults, not to zero
    assert level_for_score(30.0, {"red": 95.0}) == "blue"


def test_custom_weights_change_the_ranking_without_breaking_the_contract():
    rain_only = {**DEFAULT_WEIGHTS, "rain_intensity": 0.5, "slope": 0.0}
    wet = score_ward(
        WardInputs(rain_1h_mm=80.0, rain_3h_mm=80.0, slope_deg=5.0), weights=rain_only
    )
    dry = score_ward(WardInputs(rain_1h_mm=0.0, slope_deg=5.0), weights=rain_only)
    assert wet.score > dry.score
    slope_factor = next(f for f in wet.factors if f.key == "slope")
    assert slope_factor.weight == 0.0
    assert slope_factor.contribution == 0.0


# --------------------------------------------------------------------------- #
# crowd overlay
# --------------------------------------------------------------------------- #
def test_crowd_uplift_is_neutral_with_no_reports():
    assert crowd_uplift(0, 0, 1) == 1.0
    assert crowd_uplift(0, 0, 12) == 1.0  # corroboration alone implies no report


def test_crowd_uplift_rises_with_corroboration_and_confirmation():
    # Ordering is checked with the cap lifted, otherwise everything saturates.
    base = crowd_uplift(1, 0, 1, cap=3.0)
    corroborated = crowd_uplift(1, 0, 4, cap=3.0)
    confirmed = crowd_uplift(1, 2, 4, cap=3.0)
    loud = crowd_uplift(6, 3, 6, cap=3.0)
    assert 1.0 < base < corroborated < confirmed < loud

    # With the shipped cap the ordering still holds, it just flattens at 1.25:
    # three neighbours confirming a crack outrank one report, but no amount of
    # WhatsApp traffic outranks a *measured* gauge.
    assert crowd_uplift(1, 0, 1) < crowd_uplift(1, 2, 4) == 1.25


def test_crowd_uplift_never_exceeds_the_cap():
    for cap in (1.05, 1.1, 1.25, 2.0):
        assert crowd_uplift(999, 999, 999, reporter_trust=1.0, cap=cap) <= cap + 1e-9
    # even an unbounded flood of reports cannot pass the product default
    assert crowd_uplift(10_000, 10_000, 10_000, reporter_trust=1.0) == 1.25


def test_crowd_uplift_is_bounded_by_the_evidence_terms_it_sums():
    """0.30 corroboration + 0.45 confirmed + 0.15 open, scaled into [0.55, 1.0] by trust."""
    # Uncapped, the maximum evidence is worth +0.90 at full trust ...
    assert crowd_uplift(100, 100, 100, reporter_trust=1.0, cap=2.0) == pytest.approx(1.9)
    # ... and 0.55x as much at zero trust.
    assert crowd_uplift(100, 100, 100, reporter_trust=0.0, cap=2.0) == pytest.approx(1.495)
    # The product default clamps both long before that.
    assert crowd_uplift(100, 100, 100, reporter_trust=0.0) == 1.25
    assert crowd_uplift(1, 0, 1, reporter_trust=1.0) == pytest.approx(1.05)
    assert crowd_uplift(1, 0, 1, reporter_trust=0.0) == pytest.approx(1.0275)


def test_reporter_trust_scales_the_uplift_but_cannot_break_the_cap():
    low = crowd_uplift(1, 0, 2, reporter_trust=0.1)
    high = crowd_uplift(1, 0, 2, reporter_trust=0.9)
    assert 1.0 < low < high <= 1.25
    assert crowd_uplift(1, 0, 2, reporter_trust=5.0) == crowd_uplift(1, 0, 2, reporter_trust=1.0)
    assert crowd_uplift(1, 0, 2, reporter_trust=-3.0) == crowd_uplift(1, 0, 2, reporter_trust=0.0)


def test_score_ward_respects_a_tighter_crowd_cap():
    loud = replace(WET_STEEP_SIWALIK, open_reports=20, confirmed_reports=5)
    capped = score_ward(loud, crowd_cap=1.05)
    uncapped = score_ward(loud, crowd_cap=1.25)
    assert capped.crowd_uplift == 1.05
    assert uncapped.crowd_uplift == 1.25
    assert capped.score < uncapped.score
    assert capped.score <= 100.0 and uncapped.score <= 100.0


# --------------------------------------------------------------------------- #
# explainability
# --------------------------------------------------------------------------- #
def test_every_factor_is_explained_and_carries_its_published_weight():
    result = score_ward(WET_STEEP_SIWALIK, population=10_000)
    assert len(result.factors) == 10
    assert {f.key for f in result.factors} == set(DEFAULT_WEIGHTS)
    for factor in result.factors:
        assert factor.rationale.strip(), f"{factor.key} ships without an explanation"
        assert len(factor.rationale) > 30
        assert factor.weight == pytest.approx(DEFAULT_WEIGHTS[factor.key])
        assert 0.0 <= factor.normalised <= 1.0
        assert factor.observed >= 0.0
        assert factor.contribution == pytest.approx(
            round(factor.normalised * factor.weight * 100, 2)
        )
        assert factor.label and factor.unit


def test_factor_serialisation_is_complete_for_the_ui():
    payload = score_ward(WET_STEEP_SIWALIK).factors[0].to_dict()
    assert set(payload) == {
        "key",
        "label",
        "unit",
        "observed",
        "normalised",
        "weight",
        "contribution",
        "rationale",
    }
    assert isinstance(payload["rationale"], str)


def test_saturated_soil_never_exceeds_one_even_with_a_bigger_number():
    """Soil saturation is the one factor that may be *inferred* from the 24 h total."""
    from_probe = score_ward(WardInputs(soil_moisture=0.2, rain_24h_mm=400.0))
    factor = next(f for f in from_probe.factors if f.key == "soil_saturation")
    assert factor.normalised == pytest.approx(1.0)
    assert factor.observed == pytest.approx(1.0)
    assert 0.0 <= factor.normalised <= 1.0


def test_vegetation_deficit_is_clamped_at_both_ends():
    healthy = next(
        f for f in score_ward(WardInputs(ndvi=0.95)).factors if f.key == "vegetation_loss"
    )
    bare = next(f for f in score_ward(WardInputs(ndvi=-0.5)).factors if f.key == "vegetation_loss")
    assert healthy.normalised == 0.0
    assert bare.normalised == 1.0


def test_event_history_is_log_scaled_so_one_event_is_not_nothing():
    def norm(events: int) -> float:
        factor = next(
            f for f in score_ward(WardInputs(historical_events=events)).factors
            if f.key == "event_history"
        )
        return factor.normalised

    assert norm(0) == 0.0
    assert norm(1) > 0.2  # a single recorded failure already means something
    assert norm(12) == pytest.approx(1.0)
    assert norm(24) == 1.0  # twelve events is the documented saturation point
    # Diminishing marginal weight per extra event: 1 -> 4 is worth more per event
    # than 4 -> 12, which is worth more than 12 -> 24.
    per_event_1_4 = (norm(4) - norm(1)) / 3
    per_event_4_12 = (norm(12) - norm(4)) / 8
    assert norm(1) > per_event_1_4 > per_event_4_12 > 0


def test_high_river_stage_adds_a_toe_erosion_penalty():
    calm = next(f for f in score_ward(WardInputs(river_distance_km=1.0)).factors if f.key == "drainage")
    in_flood = next(
        f
        for f in score_ward(WardInputs(river_distance_km=1.0, river_level_m=4.5)).factors
        if f.key == "drainage"
    )
    assert in_flood.normalised > calm.normalised
    assert in_flood.normalised <= 1.0


def test_short_burst_rate_is_taken_from_the_maximum_of_one_and_three_hour_windows():
    from_one = score_ward(WardInputs(rain_1h_mm=45.0, rain_3h_mm=15.0))
    from_three = score_ward(WardInputs(rain_1h_mm=1.0, rain_3h_mm=135.0))
    factor_one = next(f for f in from_one.factors if f.key == "rain_intensity")
    factor_three = next(f for f in from_three.factors if f.key == "rain_intensity")
    assert factor_one.observed == pytest.approx(45.0)
    assert factor_three.observed == pytest.approx(45.0)  # 135/3


# --------------------------------------------------------------------------- #
# probability + exposure
# --------------------------------------------------------------------------- #
def test_probability_24h_is_monotonic_and_centred_on_the_orange_threshold():
    probs = [probability_24h(s) for s in range(0, 101)]
    assert probs == sorted(probs)
    assert all(0.0 <= p <= 1.0 for p in probs)
    assert probability_24h(DEFAULT_THRESHOLDS["orange"]) == pytest.approx(0.5)
    assert probability_24h(0) < 0.01
    assert probability_24h(100) > 0.99


def test_population_at_risk_uses_the_published_exposure_fraction():
    result = score_ward(WET_STEEP_SIWALIK, population=10_000)
    assert result.level in LEVEL_ORDER
    assert result.population_at_risk == round(10_000 * EXPOSURE_FRACTION[result.level])
    assert result.population_at_risk > 0
    assert score_ward(WET_STEEP_SIWALIK, population=0).population_at_risk == 0
    # A ward below the blue cut-off exposes nobody, by design.
    quiet = score_ward(QUIET, population=10_000)
    assert quiet.level == "green" and quiet.population_at_risk == 0


def test_exposure_fractions_are_monotonic_and_capped():
    fractions = [EXPOSURE_FRACTION[level] for level in LEVEL_ORDER]
    assert fractions == sorted(fractions)
    assert fractions[0] == 0.0
    assert fractions[-1] <= 1.0


# --------------------------------------------------------------------------- #
# confidence: how much of the number is measured
# --------------------------------------------------------------------------- #
def test_fresh_online_gauge_beats_absent_telemetry():
    measured = WardInputs(
        gauge_online=True, telemetry_age_minutes=4.0, rain_24h_mm=30.0, has_polygon=True
    )
    inferred = WardInputs(gauge_online=False, rain_24h_mm=30.0, has_polygon=True)
    assert _confidence(measured) > _confidence(inferred) + 0.2


def test_stale_telemetry_is_worth_less_than_fresh_telemetry():
    fresh = WardInputs(gauge_online=True, telemetry_age_minutes=2.0, rain_24h_mm=20.0)
    stale = WardInputs(gauge_online=True, telemetry_age_minutes=350.0, rain_24h_mm=20.0)
    assert _confidence(fresh) > _confidence(stale)


def test_confidence_stays_inside_its_documented_bounds():
    for inputs in (
        WardInputs(has_polygon=False),
        WardInputs(gauge_online=True, telemetry_age_minutes=0.0, confirmed_reports=99, rain_24h_mm=50.0),
        WardInputs(gauge_online=True, telemetry_age_minutes=None, confirmed_reports=0, open_reports=4),
        ABSURD,
    ):
        conf = _confidence(inputs)
        assert 0.10 <= conf <= 0.98, inputs
        assert conf == round(conf, 3)


def test_confidence_rewards_field_confirmation_over_unverified_rumour():
    rumour = WardInputs(open_reports=5)
    verified = WardInputs(confirmed_reports=2)
    nothing = WardInputs()
    assert _confidence(verified) > _confidence(rumour) > _confidence(nothing)


def test_score_ward_surfaces_its_confidence_and_model_version():
    result = score_ward(WET_STEEP_SIWALIK)
    assert result.confidence == _confidence(WET_STEEP_SIWALIK)
    assert result.model_version == MODEL_VERSION
    assert result.inputs is WET_STEEP_SIWALIK


# --------------------------------------------------------------------------- #
# engine <-> database glue
# --------------------------------------------------------------------------- #
@pytest.mark.slow
async def test_evaluate_wards_persists_an_auditable_breakdown(db_session):
    from app.services.risk_engine import evaluate_wards

    wards = list((await db_session.execute(select(Ward).limit(5))).scalars().all())
    assert len(wards) == 5
    before = (await db_session.execute(select(func.count(WardRisk.id)))).scalar()

    pairs = await evaluate_wards(db_session, wards)
    assert len(pairs) == 5
    for ward, score in pairs:
        assert 0.0 <= score.score <= 100.0
        assert len(score.factors) == 10
        assert score.level in LEVEL_ORDER
    await db_session.commit()

    after = (await db_session.execute(select(func.count(WardRisk.id)))).scalar()
    assert after == before + 5
    row = (
        await db_session.execute(
            select(WardRisk).where(WardRisk.ward_id == wards[0].id).order_by(WardRisk.id.desc())
        )
    ).scalars().first()
    assert row.model_version == MODEL_VERSION
    assert len(row.factors["factors"]) == 10
    assert all(f["rationale"] for f in row.factors["factors"])
    assert math.isclose(
        row.factors["base_total"], sum(f["contribution"] for f in row.factors["factors"]), abs_tol=0.05
    )
    await db_session.rollback()


@pytest.mark.slow
async def test_crowd_signals_ignores_dismissed_reports(db_session):
    from datetime import datetime, timezone

    from app.models import HazardReport
    from app.services.risk_engine import crowd_signals, crowd_uplift

    ward = (await db_session.execute(select(Ward).limit(1))).scalars().one()
    now = datetime.now(timezone.utc)
    rows = [
        HazardReport(
            code=f"TST-{ward.id}-{n}",
            ward_id=ward.id,
            district_id=ward.district_id,
            hazard_type="landslide",
            title="test signal",
            description="",
            latitude=ward.latitude,
            longitude=ward.longitude,
            status=status,
            source="app",
            corroborated_by=corrob,
            created_at=now,
        )
        for n, (status, corrob) in enumerate(
            [("confirmed", 3), ("new", 1), ("dismissed", 9), ("resolved", 9)]
        )
    ]
    db_session.add_all(rows)
    await db_session.flush()

    signals = await crowd_signals(db_session, [ward.id])
    counts = signals[ward.id]
    assert counts["confirmed"] == 1
    assert counts["open"] == 1
    # dismissed/resolved rows are excluded, so max corroboration seen is 3
    assert counts["corroboration"] == 3
    assert crowd_uplift(counts["open"], counts["confirmed"], counts["corroboration"]) > 1.0
    await db_session.rollback()

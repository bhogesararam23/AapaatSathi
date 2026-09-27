"""Tests for telemetry acquisition.

The simulator is what makes this project reviewable offline, and its value rests
on one promise: *the same inputs always produce the same hyetograph*. If that
breaks, every recorded demo, every documented score and this suite's own
assertions become unreproducible. Determinism is therefore tested as a contract,
alongside the accumulation rules the risk engine reads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.models import TelemetryReading, Ward
from app.services import ingest
from app.services.ingest import (
    HOURS_HISTORY,
    MONTHLY_BASELINE,
    HourStep,
    _live_aggregate,
    hourly_series,
    summarise,
)

END = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def as_rows(steps: list[HourStep]) -> list[tuple[str, float, bool]]:
    return [(s.at.isoformat(), s.rain_mm, s.forecast) for s in steps]


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_the_same_ward_and_hour_always_produce_the_same_series():
    first = hourly_series("PKR-RNK", end=END)
    second = hourly_series("PKR-RNK", end=END)
    assert as_rows(first) == as_rows(second)
    # ...and again after a fresh call graph, i.e. no hidden RNG state
    assert as_rows(hourly_series("PKR-RNK", end=END)) == as_rows(first)


def test_different_wards_get_different_hyetographs():
    codes = ["PKR-RNK", "UKD-DHR", "CHM-KNP", "NNT-BHM"]
    totals = {code: round(sum(s.rain_mm for s in hourly_series(code, end=END)), 3) for code in codes}
    assert len(set(totals.values())) == len(codes), totals
    assert as_rows(hourly_series("PKR-RNK", end=END)) != as_rows(hourly_series("PKR-KHR", end=END))


def test_the_end_time_is_truncated_to_the_hour_bucket():
    """12:47 and 12:00 are the same observation window, so they must agree."""
    exact = hourly_series("ALM-CLK", end=END)
    slopppy = hourly_series("ALM-CLK", end=END.replace(minute=47, second=13, microsecond=999))
    assert as_rows(exact) == as_rows(slopppy)


def test_the_series_shape_is_history_plus_a_forecast_tail():
    steps = hourly_series("PKR-RNK", end=END)
    assert len(steps) == HOURS_HISTORY + 6
    assert steps[0].at == END - timedelta(hours=HOURS_HISTORY - 1)
    assert steps[-1].at == END + timedelta(hours=6)
    assert sum(1 for s in steps if s.forecast) == 6
    assert all(s.forecast is (s.at > END) for s in steps)
    assert all(s.at.second == 0 and s.at.microsecond == 0 for s in steps)
    assert all(s.at.tzinfo is not None for s in steps)


def test_generated_values_are_non_negative_and_bounded():
    for code in ("PKR-RNK", "UKD-SIL", "RPR-PHT"):
        for step in hourly_series(code, end=END):
            assert 0.0 <= step.rain_mm < 200.0
            assert round(step.rain_mm, 2) == step.rain_mm
    assert any(step.rain_mm == 0.0 for step in hourly_series("PKR-RNK", end=END)), "dry hours exist"
    assert any(step.rain_mm > 10.0 for step in hourly_series("PKR-RNK", end=END)), "bursts exist"


def test_the_monsoon_season_is_reflected_in_the_totals():
    july = sum(s.rain_mm for s in hourly_series("PKR-RNK", end=datetime(2026, 7, 15, 12, tzinfo=timezone.utc)))
    january = sum(
        s.rain_mm for s in hourly_series("PKR-RNK", end=datetime(2026, 1, 15, 12, tzinfo=timezone.utc))
    )
    assert MONTHLY_BASELINE[7] > MONTHLY_BASELINE[1] > 0
    assert july > january * 3
    assert january < 60.0, "a winter week should not look like a cloudburst"


def test_elevation_scales_the_whole_hyetograph_proportionally():
    base = sum(s.rain_mm for s in hourly_series("TEH-JKH", end=END))
    doubled = sum(s.rain_mm for s in hourly_series("TEH-JKH", end=END, elevation_factor=2.0))
    assert doubled == pytest.approx(base * 2, abs=0.05)


def test_the_hours_argument_controls_the_window_length():
    assert len(hourly_series("PKR-RNK", end=END, hours=24)) == 24
    assert len(hourly_series("PKR-RNK", end=END, hours=HOURS_HISTORY + 6)) == HOURS_HISTORY + 6


def test_no_network_is_needed_by_default(monkeypatch):
    """The default path must never reach for Open-Meteo."""
    from app.config import settings

    def explode(*args, **kwargs):  # pragma: no cover - the guard under test
        raise AssertionError("the simulator must not call out when USE_LIVE_WEATHER is false")

    monkeypatch.setattr(settings, "use_live_weather", False)
    monkeypatch.setattr(ingest.httpx, "AsyncClient", explode)
    assert sum(s.rain_mm for s in hourly_series("PKR-RNK", end=END)) > 0


# --------------------------------------------------------------------------- #
# accumulation
# --------------------------------------------------------------------------- #
def _wet_series(now: datetime, hours: int = 72, per_hour: float = 5.0) -> list[HourStep]:
    return [
        HourStep(at=now - timedelta(hours=h), rain_mm=per_hour, forecast=False)
        for h in range(hours - 1, -1, -1)
    ]


def test_accumulations_are_monotonic_in_the_window_length():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    agg = summarise(_wet_series(now), now)
    assert agg["rain_1h_mm"] == pytest.approx(5.0)
    assert agg["rain_3h_mm"] == pytest.approx(15.0)
    assert agg["rain_24h_mm"] == pytest.approx(120.0)
    assert agg["rain_72h_mm"] == pytest.approx(360.0)
    assert agg["rain_72h_mm"] >= agg["rain_24h_mm"] >= agg["rain_3h_mm"] >= agg["rain_1h_mm"] >= 0.0
    assert agg["forecast_6h_mm"] == 0, "an all-observed series forecasts nothing"


def test_monotonic_accumulation_holds_for_a_real_generated_storm():
    now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    steps = hourly_series("PKR-RNK", end=now)
    agg = summarise(steps, now)
    assert 0 <= agg["rain_1h_mm"] <= agg["rain_3h_mm"] <= agg["rain_24h_mm"] <= agg["rain_72h_mm"]
    assert 0.0 <= agg["soil_moisture"] <= 1.0
    assert agg["rain_72h_mm"] > agg["rain_24h_mm"] > 0.0
    for key in ("rain_1h_mm", "rain_3h_mm", "rain_24h_mm", "rain_72h_mm", "forecast_6h_mm"):
        assert round(agg[key], 2) == agg[key]


def test_only_the_first_six_future_hours_feed_the_forecast_term():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    steps = _wet_series(now) + [
        HourStep(at=now + timedelta(hours=h), rain_mm=3.0, forecast=True) for h in range(1, 13)
    ]
    agg = summarise(steps, now)
    assert agg["forecast_6h_mm"] == pytest.approx(18.0), "exactly six future hours are counted"
    assert agg["rain_24h_mm"] == pytest.approx(120.0), "future rain must not inflate observations"
    assert agg["rain_72h_mm"] == pytest.approx(360.0)


def test_a_stale_feed_reads_zero_for_the_last_hour():
    """Every window, including the 1 h term, is measured from ``now``.

    The 1 h value used to anchor on ``observed[-1].at`` while 3/24/72 h anchored
    on ``now``. With a feed that stopped 49 hours ago the accumulations correctly
    read down but "last hour" still reported rain that fell two days earlier —
    presenting a dead gauge as current intensity, which is exactly the input that
    drives a cloudburst term. Staleness belongs in the confidence score, not
    hidden inside the value.
    """
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    stale = [s for s in _wet_series(now, hours=72) if s.at < now - timedelta(hours=48)]
    dried = summarise(stale, now)
    assert dried["rain_3h_mm"] == 0.0
    assert dried["rain_24h_mm"] == 0.0
    assert dried["rain_1h_mm"] == 0.0, "a 49 h-old reading is not last-hour rain"
    assert dried["rain_72h_mm"] == pytest.approx(115.0), "23 of the 72 h are still inside the window"
    assert dried["soil_moisture"] > 0.0, "recent-but-not-current rain still wets the soil"
    assert dried["soil_moisture"] < summarise(_wet_series(now), now)["soil_moisture"]


def test_soil_moisture_decays_with_age_and_saturates_at_one():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    recent = summarise([HourStep(at=now, rain_mm=40.0, forecast=False)], now)
    old = summarise([HourStep(at=now - timedelta(hours=36), rain_mm=40.0, forecast=False)], now)
    assert 0.0 < old["soil_moisture"] < recent["soil_moisture"] <= 1.0
    soaked = summarise(_wet_series(now, hours=72, per_hour=40.0), now)
    assert soaked["soil_moisture"] == 1.0


def test_an_empty_series_yields_zeros_not_an_exception():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    agg = summarise([], now)
    assert agg == {
        "rain_1h_mm": 0.0,
        "rain_3h_mm": 0.0,
        "rain_24h_mm": 0.0,
        "rain_72h_mm": 0.0,
        "forecast_6h_mm": 0.0,
        "soil_moisture": 0.0,
    }


def test_the_live_aggregator_agrees_with_the_simulator_aggregator():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    steps = _wet_series(now) + [
        HourStep(at=now + timedelta(hours=h), rain_mm=2.0, forecast=True) for h in range(1, 7)
    ]
    points = [(s.at, s.rain_mm) for s in steps]
    assert _live_aggregate(points, now) == summarise(steps, now)


def test_the_live_aggregator_refuses_to_invent_history():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    assert _live_aggregate([], now) == {}
    assert _live_aggregate([(now + timedelta(hours=1), 9.0)], now) == {}, "no observation yet"


@pytest.mark.slow
async def test_refresh_telemetry_is_reproducible_and_tags_its_source(db_session):
    """End-to-end: the same wall-clock hour writes byte-identical aggregates."""
    from app.services.assembly import all_wards

    await db_session.execute(delete(TelemetryReading))
    wards = await all_wards(db_session)
    assert len(wards) == 40

    now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    report = await ingest.refresh_telemetry(db_session, wards, use_live=False, now=now)
    assert report["source"] == "simulated"
    assert report["live_locations"] == 0
    assert report["wards"] == 40
    assert report["readings_written"] == 40
    assert report["as_of"] == now.isoformat()
    await db_session.flush()

    columns = (
        TelemetryReading.ward_id,
        TelemetryReading.rain_1h_mm,
        TelemetryReading.rain_3h_mm,
        TelemetryReading.rain_24h_mm,
        TelemetryReading.rain_72h_mm,
        TelemetryReading.soil_moisture,
        TelemetryReading.forecast_6h_mm,
        TelemetryReading.river_level_m,
        TelemetryReading.source,
    )

    async def rows() -> list[tuple]:
        result = await db_session.execute(
            select(*columns).where(TelemetryReading.recorded_at == now).order_by(TelemetryReading.id)
        )
        return list(result.all())

    first_pass = await rows()
    assert len(first_pass) == 40, first_pass
    assert all(row[8] == "simulated" for row in first_pass)
    assert {row[0] for row in first_pass} == {w.id for w in wards}
    assert all(0.0 <= row[5] <= 1.0 for row in first_pass), "soil moisture is an index"
    assert all(row[1] <= row[2] <= row[3] <= row[4] for row in first_pass), "accumulations must nest"

    # An hour later the same request must reproduce the *previous* run's numbers
    # exactly when the clock has not moved: the timestamps are truncated to the
    # hour bucket, so both runs land on ``now`` and are directly comparable.
    second_report = await ingest.refresh_telemetry(
        db_session, wards, use_live=False, now=now + timedelta(minutes=5)
    )
    await db_session.flush()
    assert second_report["readings_written"] == 40
    assert second_report["as_of"] == now.isoformat(), "run times are hour-aligned"

    both = await rows()
    assert len(both) == 80
    assert both[:40] == both[40:], "the same hour must regenerate identical telemetry"
    await db_session.rollback()


@pytest.mark.slow
async def test_injected_scenarios_are_labelled_so_they_cannot_masquerade_as_data(db_session):
    from app.models import RainGauge

    ward = (await db_session.execute(select(Ward).where(Ward.code == "DEH-KTB"))).scalars().one()
    gauge = (
        await db_session.execute(select(RainGauge).where(RainGauge.ward_id == ward.id).limit(1))
    ).scalars().first()

    reading = await ingest.inject_scenario(
        db_session,
        ward,
        rain_1h_mm=80.0,
        rain_24h_mm=200.0,
        rain_72h_mm=450.0,
        forecast_6h_mm=60.0,
        soil_moisture=0.9,
    )
    assert reading.source == "scenario"
    assert reading.ward_id == ward.id
    assert reading.gauge_id == gauge.id
    assert reading.rain_3h_mm == pytest.approx(80.0 * 2.1)
    assert reading.rain_1h_mm <= reading.rain_3h_mm <= reading.rain_24h_mm <= reading.rain_72h_mm
    # rating curve: 1.1 + 0.022 * 24h + 0.0004 * 72h
    assert reading.river_level_m == pytest.approx(1.1 + 0.022 * 200.0 + 0.0004 * 450.0, abs=0.01)

    from app.services.risk_engine import inputs_from, score_ward

    score = score_ward(inputs_from(ward, reading, None), population=ward.population)
    assert score.score > 40.0
    assert score.inputs.gauge_online is True
    assert score.confidence > 0.6
    await db_session.rollback()


@pytest.mark.slow
async def test_ward_rainfall_history_is_chart_ready_and_honest(db_session):
    from app.services.assembly import all_wards

    ward = next(w for w in await all_wards(db_session) if w.code == "RPR-PHT")
    history = await ingest.ward_rainfall_history(db_session, ward, hours=48)
    assert len(history) == 48
    assert set(history[0]) == {"at", "rain_mm", "forecast"}
    assert all(isinstance(step["rain_mm"], float) and step["rain_mm"] >= 0 for step in history)
    assert any(step["forecast"] for step in history)
    stamps = [datetime.fromisoformat(step["at"]) for step in history]
    assert stamps == sorted(stamps)
    assert all(step.tzinfo is not None for step in stamps)
    # same ward, same hour -> the same chart twice over
    assert history == await ingest.ward_rainfall_history(db_session, ward, hours=48)

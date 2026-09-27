"""Happy-path and edge-flow tests through the real ASGI application.

These exercise the routers, the read-model assembly, the crowd-report merge
logic and the scenario runner end to end: request -> dependency -> service ->
SQLAlchemy -> response contract.
"""

from __future__ import annotations

import re

import pytest

from app.services.risk_engine import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, LEVEL_ORDER, level_for_score
from tests.conftest import API, DEMO_PASSWORD

pytestmark = pytest.mark.slow

FACTOR_KEYS = set(DEFAULT_WEIGHTS)


async def file_report(
    client,
    ward: dict,
    hazard: str,
    *,
    headers: dict | None = None,
    dlat: float = 0.0,
    dlng: float = 0.0,
    title: str = "Test observation",
    severity: int = 3,
    accuracy: float = 12.0,
):
    return await client.post(
        f"{API}/reports",
        headers=headers or {},
        data={
            "hazard_type": hazard,
            "title": title,
            "description": "Observed while walking the approach track.",
            "latitude": str(ward["latitude"] + dlat),
            "longitude": str(ward["longitude"] + dlng),
            "accuracy_m": str(accuracy),
            "self_severity": str(severity),
            "ward_code": ward["code"],
            "lang": "en",
        },
    )


# --------------------------------------------------------------------------- #
# service metadata
# --------------------------------------------------------------------------- #
async def test_health_reports_the_honest_delivery_mode(client):
    res = await client.get(f"{API}/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"
    assert body["notifications"] == "console"
    assert body["simulated_delivery"] is True, "a demo must never claim real delivery"
    assert body["seed_present"] is True
    assert body["environment"] == "test"


async def test_meta_is_the_single_source_of_labels_for_the_frontend(client):
    res = await client.get(f"{API}/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["levels"] == LEVEL_ORDER
    assert body["languages"] == ["en", "hi", "gar"]
    assert body["ward_count"] == 40
    assert body["model_version"]
    assert body["telemetry"] == "simulated"
    assert body["emergency_numbers"]["control_room"] == "1070"
    assert set(body["level_names"]) == set(LEVEL_ORDER)
    for level, names in body["level_names"].items():
        assert set(names) == {"en", "hi", "gar"}
        assert all(names.values()), level
    assert set(body["report_statuses"]) == {
        "new",
        "under_review",
        "confirmed",
        "dismissed",
        "resolved",
    }
    assert body["catalog"]["report_hazard"]


async def test_districts_and_ward_listings_match_the_seed_footprint(client):
    res = await client.get(f"{API}/districts")
    assert res.status_code == 200
    districts = res.json()
    assert len(districts) == 8
    assert {d["code"] for d in districts} == {"DEH", "PKR", "TEH", "UKD", "CHM", "RPR", "ALM", "NNT"}
    assert all(d["state"] == "Uttarakhand" for d in districts)
    assert all(d["control_room"] == "1070" for d in districts)
    assert all(d["population"] > 100_000 for d in districts)

    wards = await client.get(f"{API}/wards")
    assert len(wards.json()) == 40
    pauri = await client.get(f"{API}/wards", params={"district": "PKR"})
    assert pauri.status_code == 200
    rows = pauri.json()
    assert len(rows) == 5
    assert {w["code"] for w in rows} == {"PKR-RNK", "PKR-KHR", "PKR-DWL", "PKR-STP", "PKR-DGD"}
    for ward in rows:
        assert ward["polygon"], "every seeded ward must be drawable"
        assert ward["slope_deg"] > 0 and ward["population"] > 0
        assert ward["registered_phones"] <= ward["population"]
        assert ward["connectivity"] in {"good", "mixed", "poor"}
    # lowercase filters are tolerated, unknown districts are simply empty
    assert (await client.get(f"{API}/wards", params={"district": "pkr"})).json() == rows
    assert (await client.get(f"{API}/wards", params={"district": "ZZZ"})).json() == []


# --------------------------------------------------------------------------- #
# risk surfaces
# --------------------------------------------------------------------------- #
async def test_risk_overview_scores_every_ward_with_the_full_breakdown(client):
    res = await client.get(f"{API}/risk/overview")
    assert res.status_code == 200
    body = res.json()

    assert len(body["wards"]) == 40
    for ward in body["wards"]:
        assert set(ward) >= {"code", "name", "score", "level", "confidence", "factors", "inputs"}
        assert len(ward["factors"]) == 10
        assert {f["key"] for f in ward["factors"]} == FACTOR_KEYS
        assert 0.0 <= ward["score"] <= 100.0
        assert ward["level"] == level_for_score(ward["score"])
        assert 0.10 <= ward["confidence"] <= 0.98
        assert 1.0 <= ward["crowd_uplift"] <= 1.25
        assert 0.0 <= ward["probability_24h"] <= 1.0
        assert ward["population_at_risk"] >= 0
        for factor in ward["factors"]:
            assert factor["rationale"], f"{ward['code']}/{factor['key']} has no explanation"
            assert factor["weight"] == pytest.approx(DEFAULT_WEIGHTS[factor["key"]])
            assert 0.0 <= factor["normalised"] <= 1.0

    scores = [w["score"] for w in body["wards"]]
    assert scores == sorted(scores, reverse=True), "the grid must arrive pre-sorted"
    assert body["highest"]["code"] == body["wards"][0]["code"]
    assert sum(body["levels"].values()) == 40
    assert set(body["levels"]) == set(LEVEL_ORDER)
    assert body["population_exposed"] == sum(w["population_at_risk"] for w in body["wards"])


async def test_risk_overview_filters_by_district_and_score(client):
    pauri = await client.get(f"{API}/risk/overview", params={"district": "PKR"})
    assert pauri.status_code == 200
    assert len(pauri.json()["wards"]) == 5
    assert all(w["code"].startswith("PKR-") for w in pauri.json()["wards"])

    top = max(w["score"] for w in pauri.json()["wards"])
    filtered = await client.get(f"{API}/risk/overview", params={"min_score": top})
    assert all(w["score"] >= top for w in filtered.json()["wards"])

    missing = await client.get(f"{API}/risk/overview", params={"district": "ZZZ"})
    assert missing.status_code == 404


async def test_risk_model_publishes_weights_thresholds_and_a_disclaimer(client):
    res = await client.get(f"{API}/risk/model")
    assert res.status_code == 200
    body = res.json()
    assert body["weights_sum"] == pytest.approx(1.0, abs=1e-4)
    assert body["weights"] == pytest.approx(DEFAULT_WEIGHTS)
    assert body["thresholds"] == DEFAULT_THRESHOLDS
    assert len(body["factor_docs"]) == 10
    assert {d["key"] for d in body["factor_docs"]} == FACTOR_KEYS
    for doc in body["factor_docs"]:
        assert doc["name"] and doc["source"], "every factor must cite where its data comes from"
    assert "not fitted" in body["disclaimer"].lower() or "susceptibility" in body["disclaimer"].lower()
    assert body["crowd_uplift_cap"] == 1.25


async def test_leaderboard_and_history_round_trip(client, system_headers):
    board = await client.get(f"{API}/risk/leaderboard", params={"limit": 3})
    assert board.status_code == 200
    ranked = board.json()["wards"]
    assert len(ranked) == 3
    assert [w["score"] for w in ranked] == sorted([w["score"] for w in ranked], reverse=True)

    code = ranked[0]["code"]
    # A state-wide sweep persists a row for every ward, so the trajectory below
    # exists regardless of which test ran first.
    swept = await client.post(f"{API}/risk/sweep", headers=system_headers, params={"broadcast": False})
    assert swept.status_code == 200, swept.text
    assert swept.json()["evaluated"] == 40
    history = await client.get(f"{API}/risk/history/{code}")
    assert history.status_code == 200
    assert history.json()["ward_code"] == code
    assert history.json()["points"], "a sweep must leave a replayable trajectory"
    for point in history.json()["points"]:
        assert point["level"] in LEVEL_ORDER
        assert 0.0 <= point["score"] <= 100.0

    assert (await client.get(f"{API}/risk/history/ZZZ-NOPE")).status_code == 404


# --------------------------------------------------------------------------- #
# ward detail: shelters, roads, hyetograph
# --------------------------------------------------------------------------- #
async def test_ward_detail_carries_assets_and_an_honest_rainfall_series(client):
    res = await client.get(f"{API}/wards/PKR-RNK")
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == "PKR-RNK"
    assert len(body["factors"]) == 10
    assert body["polygon"] and len(body["polygon"]) >= 3
    assert body["notes"], "Ranikhot should carry its 2021 context"

    assert body["nearest_shelters"], "a warning without a destination is useless"
    distances = [s["distance_km"] for s in body["nearest_shelters"]]
    assert distances == sorted(distances)
    for shelter in body["nearest_shelters"]:
        assert shelter["free_places"] == max(0, shelter["capacity"] - shelter["occupied"])
        assert 0.0 <= shelter["bearing_deg"] < 360.0

    series = body["rainfall_series"]
    assert len(series) == 48
    assert all(step["rain_mm"] >= 0.0 for step in series)
    assert any(step["forecast"] for step in series), "the series must show the forecast tail"

    recent = body["recent_reports"]
    assert all(r["code"].startswith("HR") for r in recent)
    assert all("reporter_id" not in r for r in recent)


async def test_ward_series_endpoint_exposes_gauge_state(client):
    res = await client.get(f"{API}/geo/wards/UKD-DHR/series", params={"hours": 24})
    assert res.status_code == 200
    body = res.json()
    assert body["ward_code"] == "UKD-DHR"
    assert len(body["rainfall"]) == 24
    assert body["gauges"], "every seeded ward has at least one rain gauge"
    assert all(g["status"] in {"online", "offline", "maintenance"} for g in body["gauges"])
    assert body["current"]["score"] is not None
    assert 0.0 <= body["current"]["score"] <= 100.0
    assert body["current"]["model_version"]


async def test_choropleth_endpoint_returns_one_feature_per_ward(client):
    """The live endpoint is a *polygon* layer, matching its name and docstring.

    Each feature carries a closed ring plus the properties the map needs, so a
    client can style ward boundaries without fetching every ward individually.
    """
    res = await client.get(f"{API}/geo/choropleth")
    assert res.status_code == 200
    body = res.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 40
    codes = set()
    for feature in body["features"]:
        assert feature["geometry"]["type"] == "Polygon"
        ring = feature["geometry"]["coordinates"][0]
        assert len(ring) >= 4, "a ring needs at least 3 distinct points plus a closure"
        assert ring[0] == ring[-1], "rings must be closed for GeoJSON"
        for lng, lat in ring:
            assert -180 <= lng <= 180 and -90 <= lat <= 90
        props = feature["properties"]
        assert props["level"] in LEVEL_ORDER
        assert 0.0 <= props["score"] <= 100.0
        assert 0.10 <= props["confidence"] <= 0.98
        assert props["population_at_risk"] <= props["population"]
        codes.add(props["code"])
    assert len(codes) == 40, "no ward may be duplicated or dropped"

    pauri = await client.get(f"{API}/geo/choropleth", params={"district": "PKR"})
    assert len(pauri.json()["features"]) == 5
    assert (await client.get(f"{API}/geo/choropleth", params={"district": "ZZZ"})).status_code == 404


async def test_polygon_choropleth_builds_closed_geojson_rings(db_session):
    """The service-layer variant must emit valid, closed polygons for the map."""
    from app.services import assembly

    layer = await assembly.choropleth(db_session)
    assert layer["type"] == "FeatureCollection"
    assert len(layer["features"]) == 40
    for feature in layer["features"]:
        assert feature["geometry"]["type"] == "Polygon"
        ring = feature["geometry"]["coordinates"][0]
        assert len(ring) >= 4, "a ward outline needs at least three distinct corners"
        assert ring[0] == ring[-1], "GeoJSON polygons must be closed"
        assert feature["properties"]["level"] in LEVEL_ORDER


# --------------------------------------------------------------------------- #
# crowd reports
# --------------------------------------------------------------------------- #
async def test_filing_then_corroborating_raises_the_corroboration_count(client, ward_lookup):
    ward = await ward_lookup("NNT-MKN")
    filed = await file_report(client, ward, "landslide", dlat=0.0007, dlng=-0.0004, severity=4)
    assert filed.status_code == 201, filed.text
    first = filed.json()
    assert first["merged"] is False
    assert first["report"]["corroborated_by"] == 1
    code = first["report"]["code"]
    baseline = first["confidence"]["value"]

    async def corroborate():
        return await client.post(f"{API}/reports/{code}/corroborate")

    numbers = []
    for _ in range(2):
        res = await corroborate()
        assert res.status_code == 200, res.text
        numbers.append(res.json()["corroborated_by"])
        assert 0.0 <= res.json()["confidence"] <= 1.0
    assert numbers == [2, 3]

    detail = await client.get(f"{API}/reports/{code}")
    assert detail.status_code == 200
    assert detail.json()["corroborated_by"] == 3
    assert detail.json()["confidence"] >= baseline
    assert detail.json()["confidence_components"]["corroborated_by"] == 3

    nearby = await client.post(
        f"{API}/reports/nearby",
        json={"latitude": ward["latitude"], "longitude": ward["longitude"], "radius_km": 2},
    )
    assert nearby.status_code == 200
    assert code in [r["code"] for r in nearby.json()["reports"]]


async def test_a_reporter_cannot_double_file_but_a_neighbour_can_merge(client, citizen_headers, ward_lookup):
    ward = await ward_lookup("ALM-KSN")

    first = await file_report(client, ward, "earthquake", headers=citizen_headers, dlat=0.0005)
    assert first.status_code == 201, first.text
    code = first.json()["report"]["code"]
    assert first.json()["report"]["source"] == "web", "an authenticated submission is attributable"

    again = await file_report(client, ward, "earthquake", headers=citizen_headers, dlat=0.0006)
    assert again.status_code == 409, again.text
    assert "already reported" in again.json()["detail"]

    neighbour = await file_report(client, ward, "earthquake", dlat=0.0007, dlng=0.0002)
    assert neighbour.status_code == 201, neighbour.text
    merged = neighbour.json()
    assert merged["merged"] is True
    assert merged["report"]["code"] == code, "the cluster keeps the original identity"
    assert merged["report"]["corroborated_by"] == 2
    assert merged["confidence"]["components"]["corroboration"] > 0.0

    stats = await client.get(f"{API}/reports/stats")
    assert stats.status_code == 200
    assert stats.json()["total"] >= 12, "the seeded reports are still counted"


async def test_report_confidence_is_explained_and_staff_verdicts_move_trust(client, field_headers, ward_lookup):
    ward = await ward_lookup("CHM-JST")
    filed = await file_report(client, ward, "debris_flow", title="Slurry over the shoulder", severity=5)
    assert filed.status_code == 201, filed.text
    body = filed.json()
    confidence = body["confidence"]
    assert set(confidence["components"]) == {
        "reporter_trust",
        "corroboration",
        "evidence",
        "severity_signal",
        "geo_plausibility",
    }
    assert sum(confidence["weights"].values()) == pytest.approx(1.0)
    recomputed = sum(confidence["weights"][k] * confidence["components"][k] for k in confidence["weights"])
    assert confidence["value"] == pytest.approx(recomputed, abs=1e-3)
    assert 0.0 <= confidence["value"] <= 1.0

    code = body["report"]["code"]
    denied = await client.patch(f"{API}/reports/{code}/verdict", json={"status": "confirmed"})
    assert denied.status_code == 401

    confirmed = await client.patch(
        f"{API}/reports/{code}/verdict",
        json={"status": "confirmed", "note": "Verified on site, one lane closed."},
        headers=field_headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["report"]["status"] == "confirmed"
    assert confirmed.json()["report"]["confidence"] >= 0.9
    assert confirmed.json()["report"]["resolution_note"].startswith("Verified")

    dispatched = await client.post(f"{API}/reports/{code}/dispatch", headers=field_headers)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["responders_dispatched"] == 1

    assert (await client.get(f"{API}/reports/HR-DOES-NOT-EXIST")).status_code == 404


async def test_reports_reject_impossible_input(client):
    res = await client.post(
        f"{API}/reports",
        data={
            "hazard_type": "landslide",
            "title": "Down under",
            "latitude": "999",
            "longitude": "0",
        },
    )
    assert res.status_code == 422, res.text
    assert "out of range" in res.json()["detail"]

    unknown_hazard = await client.post(
        f"{API}/reports",
        data={"hazard_type": "volcanic_eruption", "latitude": "30.1", "longitude": "78.2"},
    )
    assert unknown_hazard.status_code == 422

    offmap = await client.post(
        f"{API}/reports",
        data={"hazard_type": "landslide", "latitude": "-33.8", "longitude": "151.2"},
    )
    assert offmap.status_code == 422, "a location outside the ward map cannot be filed"


# --------------------------------------------------------------------------- #
# scenario runner
# --------------------------------------------------------------------------- #
async def test_an_impossible_hyetograph_is_rejected(client, admin_headers):
    res = await client.post(
        f"{API}/risk/scenario",
        headers=admin_headers,
        json={
            "ward_code": "DEH-KTB",
            "rain_1h_mm": 180.0,  # more in one hour than in a day
            "rain_24h_mm": 60.0,
            "rain_72h_mm": 200.0,
            "forecast_6h_mm": 40.0,
            "soil_moisture": 0.9,
        },
    )
    assert res.status_code == 422, res.text
    body = res.json()
    assert body["detail"] == "Check the highlighted fields"
    assert any("rain_1h_mm" in message for message in body["fields"].values()), body["fields"]

    backwards = await client.post(
        f"{API}/risk/scenario",
        headers=admin_headers,
        json={
            "ward_code": "DEH-KTB",
            "rain_1h_mm": 10.0,
            "rain_24h_mm": 300.0,
            "rain_72h_mm": 120.0,  # a day cannot exceed three days
            "forecast_6h_mm": 10.0,
            "soil_moisture": 0.5,
        },
    )
    assert backwards.status_code == 422

    too_wet = await client.post(
        f"{API}/risk/scenario",
        headers=admin_headers,
        json={
            "ward_code": "DEH-KTB",
            "rain_1h_mm": 10.0,
            "rain_24h_mm": 30.0,
            "rain_72h_mm": 60.0,
            "forecast_6h_mm": 10.0,
            "soil_moisture": 4.0,  # outside 0..1
        },
    )
    assert too_wet.status_code == 422


async def test_a_citizen_cannot_drive_a_scenario(client, citizen_headers):
    res = await client.post(
        f"{API}/risk/scenario",
        headers=citizen_headers,
        json={
            "ward_code": "DEH-KTB",
            "rain_1h_mm": 90.0,
            "rain_24h_mm": 200.0,
            "rain_72h_mm": 400.0,
            "forecast_6h_mm": 80.0,
            "soil_moisture": 0.9,
        },
    )
    assert res.status_code == 403


async def test_scenario_runner_escalates_a_quiet_ward_to_orange_or_red(client, admin_headers):
    before = await client.get(f"{API}/wards/DEH-KTB")
    assert before.status_code == 200
    quiet = before.json()
    assert quiet["score"] < 62.0, "Kantabagh should start the drill below orange"

    res = await client.post(
        f"{API}/risk/scenario",
        headers=admin_headers,
        json={
            "ward_code": "DEH-KTB",
            "rain_1h_mm": 140.0,
            "rain_24h_mm": 400.0,
            "rain_72h_mm": 600.0,
            "forecast_6h_mm": 120.0,
            "soil_moisture": 1.0,
            "broadcast": False,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    ward = body["ward"]

    assert ward["score"] >= 62.0, ward["score"]
    assert ward["level"] in {"orange", "red"}
    assert ward["score"] > quiet["score"]
    assert body["escalation"] is None, "broadcast=False must not message anyone"
    assert "scenario" in body["note"], "drill telemetry has to be labelled as such"
    assert ward["inputs"]["rain_1h_mm"] == 140.0
    assert ward["inputs"]["rain_72h_mm"] == 600.0
    assert len(ward["factors"]) == 10

    rain = next(f for f in ward["factors"] if f["key"] == "rain_intensity")
    assert rain["normalised"] > 0.9
    assert rain["contribution"] > 0

    after = await client.get(f"{API}/wards/DEH-KTB")
    assert after.json()["level"] in {"orange", "red"}, "the escalation must survive the request"


# --------------------------------------------------------------------------- #
# alerts and delivery accounting
# --------------------------------------------------------------------------- #
async def test_broadcast_records_simulated_delivery_and_can_be_proved(client, admin_headers, system_headers):
    created = await client.post(
        f"{API}/alerts",
        headers=admin_headers,
        json={
            "ward_code": "DEH-KTB",
            "hazard_type": "flash_flood",
            "level": "yellow",
            "title": "Rapid rise below the Kantabagh outfall",
            "broadcast": True,
            "channels": ["sms"],
            "ttl_minutes": 120,
        },
    )
    assert created.status_code == 201, created.text
    alert = created.json()
    assert alert["delivered"] > 0, "a broadcast must record its own reach"
    assert alert["reach_target"] > 0
    assert alert["auto_issued"] is False

    live = await client.get(f"{API}/alerts/live")
    assert live.status_code == 200
    codes = [a["code"] for a in live.json()["alerts"]]
    assert alert["code"] in codes
    for row in live.json()["alerts"]:
        assert row["minutes_left"] is None or row["minutes_left"] >= 0
        assert row["ward_name"]

    stats = (await client.get(f"{API}/notifications/stats", headers=system_headers)).json()
    assert stats["provider"] == "console"
    assert stats["simulated"] is True
    assert "sent" not in stats["by_status"], "console traffic must never be booked as delivered"
    assert stats["by_status"]["simulated"] >= alert["delivered"]
    assert "SIMULATED" in stats["note"]

    listed = (
        await client.get(
            f"{API}/notifications", headers=system_headers, params={"alert_code": alert["code"], "limit": 50}
        )
    ).json()
    assert listed["count"] > 0
    for row in listed["notifications"]:
        assert row["status"] == "simulated"
        assert not re.search(r"\d{8,}", row["phone"] or ""), "the list view must mask phone numbers"

    revoked = await client.patch(
        f"{API}/alerts/{alert['code']}/status",
        headers=admin_headers,
        json={"status": "revoked"},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"
    assert alert["code"] not in [a["code"] for a in (await client.get(f"{API}/alerts/live")).json()["alerts"]]


async def test_acknowledgements_are_counted_for_the_console_metric(client, admin_headers, citizen_headers):
    created = await client.post(
        f"{API}/alerts",
        headers=admin_headers,
        json={
            "ward_code": "DEH-MUS",
            "hazard_type": "landslide",
            "level": "orange",
            "broadcast": False,
        },
    )
    assert created.status_code == 201, created.text
    code = created.json()["code"]
    assert created.json()["channels"] == ["sms", "ivr"]

    first = await client.post(f"{API}/alerts/{code}/acknowledge", headers=citizen_headers)
    second = await client.post(f"{API}/alerts/{code}/acknowledge", headers=citizen_headers)
    assert first.json()["acknowledged"] == 1
    assert second.json()["acknowledged"] == 2

    staff_ack = await client.post(f"{API}/alerts/{code}/acknowledge", headers=admin_headers)
    assert staff_ack.json()["acknowledged"] == 3
    fetched = await client.get(f"{API}/alerts/{code}")
    assert fetched.json()["status"] == "acknowledged", "a staff ack promotes the alert state"

    preview = await client.post(
        f"{API}/alerts/preview",
        headers=admin_headers,
        json={"ward_code": "DEH-MUS", "hazard_type": "landslide", "level": "orange"},
    )
    assert preview.status_code == 200, preview.text
    assert set(preview.json()["messages"]) == {"en", "hi", "gar"}
    assert "EVACUATE" not in preview.json()["messages"]["en"]["sms"]


async def test_alert_validation_rejects_a_targetless_warning(client, admin_headers):
    res = await client.post(
        f"{API}/alerts",
        headers=admin_headers,
        json={"hazard_type": "landslide", "level": "yellow"},
    )
    assert res.status_code == 422
    assert (await client.get(f"{API}/alerts/NO-SUCH-ALERT")).status_code == 404


# --------------------------------------------------------------------------- #
# response assets and analytics
# --------------------------------------------------------------------------- #
async def test_shelter_capacity_updates_derive_their_own_status(client, field_headers):
    listing = await client.get(f"{API}/shelters", params={"ward": "PKR-KHR"})
    assert listing.status_code == 200
    assert listing.json()["count"] == 1, "Khirsu carries the seeded community hall"
    shelter = listing.json()["shelters"][0]

    filled = await client.patch(
        f"{API}/shelters/{shelter['code']}",
        headers=field_headers,
        json={"occupied": shelter["capacity"]},
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["status"] == "overflow"
    assert filled.json()["free_places"] == 0
    assert filled.json()["occupancy_pct"] == 100.0

    reopened = await client.patch(
        f"{API}/shelters/{shelter['code']}",
        headers=field_headers,
        json={"occupied": max(0, shelter["capacity"] // 10)},
    )
    assert reopened.json()["status"] == "open"
    assert reopened.json()["free_places"] > 0

    with_space = await client.get(f"{API}/shelters", params={"only_space": True, "limit": 500})
    assert all(s["free_places"] > 0 for s in with_space.json()["shelters"])
    assert with_space.json()["total_free"] == sum(s["free_places"] for s in with_space.json()["shelters"])

    created = await client.post(
        f"{API}/shelters",
        headers=field_headers,
        json={"name": "Drill Hall", "ward_code": "PKR-DWL", "kind": "community_hall", "capacity": 150},
    )
    assert created.status_code == 201, created.text
    assert created.json()["ward_name"]
    assert created.json()["code"].startswith("SH-")


async def test_shelter_writes_need_staff(client, citizen_headers):
    res = await client.post(
        f"{API}/shelters",
        headers=citizen_headers,
        json={"name": "Not Allowed Hall", "ward_code": "DEH-MUS", "capacity": 10},
    )
    assert res.status_code == 403


async def test_road_status_updates_are_attributed(client, field_headers):
    roads = await client.get(f"{API}/roads", params={"district": "PKR"})
    assert roads.status_code == 200
    rows = roads.json()["roads"]
    assert rows
    assert roads.json()["by_status"]["open"] + roads.json()["by_status"]["closed"] <= roads.json()["count"]

    target = next(r for r in rows if r["is_lifeline"])
    updated = await client.patch(
        f"{API}/roads/{target['code']}/status",
        headers=field_headers,
        json={"status": "closed", "note": "Debris across both lanes", "clearance_eta_hours": 6},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["previous"] == "open"
    assert updated.json()["status"] == "closed"

    blocked = await client.get(f"{API}/roads", params={"district": "PKR", "blocked_only": True})
    assert target["code"] in [r["code"] for r in blocked.json()["roads"]]
    assert blocked.json()["lifelines_blocked"] >= 1

    back = await client.patch(
        f"{API}/roads/{target['code']}/status",
        headers=field_headers,
        json={"status": "open", "note": "Cleared by PWD"},
    )
    assert back.json()["status"] == "open"

    assert (await client.patch(f"{API}/roads/NOPE/status", headers=field_headers, json={"status": "open"})).status_code == 404


async def test_anonymous_users_cannot_edit_response_assets(client):
    res = await client.patch("/api/v1/shelters/SH-X", json={"occupied": 5})
    assert res.status_code == 401
    res = await client.patch(
        f"{API}/roads/NH73-BHAIRON/status", json={"status": "closed", "note": "lol"}
    )
    assert res.status_code == 401


async def test_analytics_summary_agrees_with_the_other_surfaces(client):
    res = await client.get(f"{API}/analytics/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["wards"] == 40
    assert body["districts"] == 8
    assert sum(body["levels"].values()) == 40
    assert body["population_covered"] > 100_000
    assert body["phones_reachable"] <= body["population_covered"]
    assert body["shelters"] > 0
    assert body["roads_total"] > 0
    assert body["telemetry_source"] in {"simulated", "open-meteo", "scenario", "none"}
    assert 0.10 <= body["mean_confidence"] <= 0.98
    assert body["median_lead_minutes"] is None or body["median_lead_minutes"] >= 0

    coverage = (await client.get(f"{API}/analytics/coverage")).json()
    assert len(coverage["districts"]) == 8
    assert sum(d["wards"] for d in coverage["districts"]) == 40
    for district in coverage["districts"]:
        assert 0.0 <= district["mean_score"] <= 100.0
        assert district["worst_level"] in LEVEL_ORDER

    timeseries = (await client.get(f"{API}/analytics/timeseries", params={"hours": 24})).json()
    assert timeseries["hours"] == 24
    assert isinstance(timeseries["points"], list)


async def test_subscriptions_round_trip_for_a_signed_in_resident(client, citizen_headers):
    initial = await client.get(f"{API}/me/subscriptions", headers=citizen_headers)
    assert initial.status_code == 200
    assert any(s["ward_code"] == "PKR-RNK" for s in initial.json())

    subscribe = await client.post(
        f"{API}/me/subscriptions/DEH-NGN",
        headers=citizen_headers,
        params={"channel": "sms", "lang": "gar", "min_level": "orange"},
    )
    assert subscribe.status_code == 200, subscribe.text
    assert subscribe.json()["ward"] == "DEH-NGN"
    assert subscribe.json()["lang"] == "gar"

    listed = await client.get(f"{API}/me/subscriptions", headers=citizen_headers)
    assert any(s["ward_code"] == "DEH-NGN" for s in listed.json())

    gone = await client.delete(f"{API}/me/subscriptions/DEH-NGN", headers=citizen_headers)
    assert gone.status_code == 200
    assert gone.json()["message"] == "Unsubscribed"
    assert (await client.delete(f"{API}/me/subscriptions/DEH-NGN", headers=citizen_headers)).status_code == 404

    bad = await client.post(
        f"{API}/me/subscriptions/DEH-NGN", headers=citizen_headers, params={"channel": "carrier-pigeon"}
    )
    assert bad.status_code == 422


async def test_a_resident_can_update_their_profile_and_language(client, unique_email):
    registered = await client.post(
        f"{API}/auth/register",
        json={
            "full_name": "Vimla Bhandari",
            "email": unique_email,
            "password": DEMO_PASSWORD,
            "ward_code": "UKD-BHW",
            "preferred_lang": "hi",
        },
    )
    assert registered.status_code == 201, registered.text
    tokens = registered.json()
    assert tokens["user"]["ward_id"]
    assert tokens["expires_in"] > 0
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    patched = await client.patch(
        f"{API}/auth/me", headers=headers, json={"preferred_lang": "gar", "ward_code": "UKD-SIL"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["preferred_lang"] == "gar"

    me = await client.get(f"{API}/auth/me", headers=headers)
    assert me.json()["email"] == unique_email
    assert me.json()["role"] == "citizen"
    assert me.json()["is_active"] is True
    assert "hashed_password" not in me.json()

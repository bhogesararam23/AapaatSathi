"""End-to-end smoke test against a running AapaatSathi API.

    python scripts/smoke_test.py [--base http://127.0.0.1:8000]

Exercises the flows that actually matter: sign in at each role, read the risk
map, file a hazard report anonymously and as a citizen, corroborate it, confirm
it as staff, run a what-if scenario that escalates a ward to red, broadcast a
warning, and prove the delivery ledger recorded it as simulated rather than
pretending it was sent.

Exit code 0 means every check passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx

PASS, FAIL = "\033[32m  PASS\033[0m", "\033[31m  FAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{PASS if ok else FAIL}  {name}" + (f"  \033[2m{detail}\033[0m" if detail else ""))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--prefix", default="/api/v1")
    args = ap.parse_args()
    root = args.base.rstrip("/") + args.prefix
    api = httpx.Client(base_url=root, timeout=45.0)

    print(f"\n\033[1mAapaatSathi smoke test\033[0m against {root}\n")

    # ---------------------------------------------------------------- health
    r = api.get("/health")
    check("GET /health responds", r.status_code == 200, r.text[:70] if r.status_code != 200 else "")
    body: dict[str, Any] = r.json() if r.status_code == 200 else {}
    check("seed data present", bool(body.get("seed_present")))
    check("delivery is simulated by default", body.get("simulated_delivery") is True)

    r = api.get("/meta")
    check("GET /meta exposes levels + hazards", r.status_code == 200 and "levels" in r.json())

    # -------------------------------------------------------------- geography
    r = api.get("/districts")
    districts = r.json() if r.status_code == 200 else []
    check("8 districts seeded", len(districts) == 8, f"got {len(districts)}")

    r = api.get("/wards", params={"district": "PKR"})
    wards = r.json() if r.status_code == 200 else []
    check("wards filtered by district", len(wards) == 5, f"got {len(wards)}")
    if not wards:
        return finish(api)

    r = api.get("/risk/overview")
    ov = r.json() if r.status_code == 200 else {}
    check("risk overview returns scored wards", len(ov.get("wards", [])) >= 30)
    check("overview reports exposed population", "population_exposed" in ov)
    levels = ov.get("levels", {})
    check("levels tally sums to ward count", sum(levels.values()) == len(ov.get("wards", [])))

    top = max(ov.get("wards", []), key=lambda w: w["score"], default={})
    check(
        "highest-risk ward carries a factor breakdown",
        len(top.get("factors", [])) == 10,
        f"{top.get('code')} score={top.get('score')} factors={len(top.get('factors', []))}",
    )
    check(
        "every factor is explained (rationale + weight)",
        all(f.get("rationale") and f.get("weight", 0) > 0 for f in top.get("factors", [])),
    )

    r = api.get("/risk/model")
    model = r.json() if r.status_code == 200 else {}
    check("weights published and sum to 1.0", abs(model.get("weights_sum", 0) - 1.0) < 1e-6)
    check("model ships an honesty disclaimer", bool(model.get("disclaimer")))

    r = api.get(f"/wards/{top.get('code', 'PKR-RNK')}")
    ward_detail = r.json() if r.status_code == 200 else {}
    check("ward detail includes nearby shelters", len(ward_detail.get("nearest_shelters", [])) > 0)
    check("ward detail includes rainfall hyetograph", len(ward_detail.get("rainfall_series", [])) > 10)
    check("ward detail includes road status", "roads" in ward_detail)

    r = api.get("/geo/choropleth")
    check("choropleth is valid GeoJSON", r.status_code == 200 and r.json().get("type") == "FeatureCollection")

    # ------------------------------------------------------------------- auth
    r = api.post("/auth/login", json={"identifier": "admin.demo@aapaatsathi.in", "password": "Aapaat@2026"})
    check("system admin can sign in", r.status_code == 200)
    admin = r.json()["access_token"] if r.status_code == 200 else ""

    r = api.post("/auth/login", json={"identifier": "collector.demo@aapaatsathi.in", "password": "Aapaat@2026"})
    collector = r.json()["access_token"] if r.status_code == 200 else ""
    check("district admin can sign in", bool(collector))

    r = api.post("/auth/login", json={"identifier": "field.demo@aapaatsathi.in", "password": "Aapaat@2026"})
    field = r.json()["access_token"] if r.status_code == 200 else ""
    check("field responder can sign in", bool(field))

    r = api.post("/auth/login", json={"identifier": "citizen.demo@aapaatsathi.in", "password": "wrong-password"})
    check("bad password is rejected", r.status_code == 401)

    r = api.post("/auth/register", json={
        "full_name": "Privilege Escalation Tester",
        "email": "sneaky@example.org",
        "password": "Passw0rd!",
        "role": "district_admin",
    })
    if r.status_code == 201:
        check("self-registration cannot mint an admin", r.json()["user"]["role"] == "citizen",
              f"got role={r.json()['user']['role']}")
    else:
        check("self-registration cannot mint an admin", True, f"rejected with {r.status_code}")

    A = {"Authorization": f"Bearer {admin}"}
    C = {"Authorization": f"Bearer {collector}"}
    F = {"Authorization": f"Bearer {field}"}

    # -------------------------------------------------------- role boundaries
    r = api.post("/risk/sweep", params={"broadcast": "false"})
    check("anonymous cannot trigger a sweep", r.status_code in (401, 403), f"got {r.status_code}")
    r = api.post("/risk/sweep", headers=F, params={"broadcast": "false"})
    check("field responder cannot trigger a sweep", r.status_code in (401, 403), f"got {r.status_code}")
    r = api.get("/analytics/audit", headers=A)
    check("system admin can read the audit trail", r.status_code == 200)

    # ------------------------------------------------------------- reporting
    r = api.post("/reports", data={
        "hazard_type": "landslide",
        "title": "Smoke test crack",
        "description": "Automated verification report",
        "latitude": wards[0]["latitude"] + 0.0004,
        "longitude": wards[0]["longitude"] - 0.0004,
        "accuracy_m": 12,
        "self_severity": 4,
        "ward_code": wards[0]["code"],
        "lang": "hi",
    })
    ok = r.status_code == 201
    new_report = r.json() if ok else {}
    check("anonymous citizen can file a hazard report", ok, f"{r.status_code} {r.text[:90] if not ok else ''}")
    conf = new_report.get("confidence", {})
    check("report confidence is decomposed, not a black box",
          bool(conf.get("components")) and abs(sum(conf.get("weights", {}).values()) - 1.0) < 1e-6)

    code = new_report.get("report", {}).get("code", "")
    if code:
        r = api.post(f"/reports/{code}/corroborate", headers=C)
        check("a neighbour can corroborate the report", r.status_code == 200 and r.json().get("corroborated_by", 0) >= 2)
        r = api.patch(f"/reports/{code}/verdict", headers=F, json={"status": "confirmed", "note": "verified on site"})
        check("responder can confirm the report", r.status_code == 200)
        r = api.post(f"/reports/{code}/dispatch", headers=C)
        check("admin can dispatch a team", r.status_code == 200)
        r = api.patch(f"/reports/{code}/verdict", headers={"Authorization": "Bearer"}, json={"status": "confirmed"})
        check("anonymous cannot adjudicate a report", r.status_code in (401, 403))

    r = api.post("/reports", data={
        "hazard_type": "landslide", "title": "dupe", "description": "dupe",
        "latitude": wards[0]["latitude"] + 0.0004, "longitude": wards[0]["longitude"] - 0.0004,
        "ward_code": wards[0]["code"],
    })
    check("a duplicate report merges instead of clustering", r.status_code == 201 and r.json().get("merged") is True)

    r = api.get("/reports", params={"needs_review": "true", "status": "new"})
    check("triage queue lists open reports", r.status_code == 200 and "reports" in r.json())

    # ------------------------------------------------------------- scenario
    r = api.get("/risk/overview")
    quiet = min(r.json()["wards"], key=lambda w: w["score"])
    r = api.post("/risk/scenario", headers=A, json={
        "ward_code": quiet["code"],
        "rain_1h_mm": 96,
        "rain_24h_mm": 210,
        "rain_72h_mm": 340,
        "forecast_6h_mm": 70,
        "soil_moisture": 0.92,
        "broadcast": False,
    })
    ok = r.status_code == 200
    after = r.json().get("ward", {}) if ok else {}
    check("what-if scenario runner accepts an injection", ok, f"{r.status_code} {r.text[:90] if not ok else ''}")
    check("scenario escalates the ward", after.get("level") in ("orange", "red"),
          f"{quiet['code']}: {quiet['level']} -> {after.get('level')} score={after.get('score')}")
    check("scenario is tagged, never presented as an observation", "scenario" in r.text)

    r = api.post("/risk/scenario", headers=A, json={
        "ward_code": quiet["code"], "rain_1h_mm": 400, "rain_24h_mm": 10,
        "rain_72h_mm": 500, "forecast_6h_mm": 10, "soil_moisture": 0.5,
    })
    check("physically impossible scenario is refused", r.status_code == 422)

    # --------------------------------------------------------------- alerts
    r = api.get("/alerts/live")
    check("live alerts endpoint works", r.status_code == 200 and "alerts" in r.json())

    r = api.post("/alerts/preview", headers=A, json={
        "ward_code": "PKR-RNK", "hazard_type": "landslide", "level": "red", "broadcast": False,
    })
    prev = r.json() if r.status_code == 200 else {}
    langs = set(prev.get("messages", {}).keys())
    check("preview renders all three languages", {"en", "hi", "gar"} <= langs, f"got {sorted(langs)}")
    check("preview separates real subscribers from simulated reach",
          "real_recipients" in prev and "estimated_reach" in prev)

    r = api.post("/alerts", headers=A, json={
        "ward_code": "PKR-RNK", "hazard_type": "landslide", "level": "orange",
        "channels": ["sms", "ivr"], "broadcast": True, "ttl_minutes": 90,
    })
    ok = r.status_code == 201
    alert_code = r.json().get("code", "") if ok else ""
    check("admin can author and broadcast an alert", ok, f"{r.status_code} {r.text[:90] if not ok else ''}")
    check("broadcast accounts for reach", ok and r.json().get("delivered", 0) > 0,
          f"delivered={r.json().get('delivered') if ok else 0}")

    if alert_code:
        r = api.post(f"/alerts/{alert_code}/acknowledge", headers=C)
        check("a signed-in user can acknowledge an alert", r.status_code == 200)
        r = api.patch(f"/alerts/{alert_code}/status", headers=A, json={"status": "revoked"})
        check("admin can revoke an alert", r.status_code == 200 and r.json().get("status") == "revoked")

    r = api.get("/notifications/stats", headers=A)
    stats = r.json() if r.status_code == 200 else {}
    check("delivery ledger is readable", bool(stats))
    check("simulated sends are labelled simulated, not sent",
          stats.get("simulated") is True and stats.get("by_status", {}).get("simulated", 0) > 0,
          json.dumps(stats.get("by_status", {}))[:80])

    # ------------------------------------------------------------- response
    r = api.get("/shelters", params={"lat": 30.125, "lng": 78.225, "only_space": "true"})
    shelters = r.json().get("shelters", []) if r.status_code == 200 else []
    check("shelters sort by distance with live free space",
          len(shelters) > 0 and shelters[0].get("distance_km", 1e9) <= shelters[-1].get("distance_km", 0))
    if shelters:
        r = api.patch(f"/shelters/{shelters[0]['code']}", headers=F, json={"occupied": 12, "note": "smoke"})
        check("responder can update shelter occupancy", r.status_code == 200 and r.json().get("free_places", -1) >= 0)

    r = api.get("/roads")
    roads = r.json().get("roads", []) if r.status_code == 200 else []
    check("road network is seeded", len(roads) >= 15, f"got {len(roads)}")
    if roads:
        target = roads[0]["code"]
        r = api.patch(f"/roads/{target}/status", headers=F, json={"status": "closed", "note": "debris", "clearance_eta_hours": 6})
        check("responder can close a road", r.status_code == 200 and r.json().get("status") == "closed")
        r = api.patch(f"/roads/{target}/status", headers={"Authorization": "Nope"}, json={"status": "open"})
        check("anonymous cannot reopen a road", r.status_code in (401, 403))
        api.patch(f"/roads/{target}/status", headers=A, json={"status": "open", "note": "cleared"})

    r = api.get("/resources")
    check("deployable resources are tracked", r.status_code == 200 and len(r.json()) >= 10)

    # ------------------------------------------------------------ analytics
    r = api.get("/analytics/summary")
    an = r.json() if r.status_code == 200 else {}
    check("analytics summary computes coverage", an.get("wards", 0) >= 30 and an.get("population_covered", 0) > 100_000,
          f"{an.get('wards')} wards / {an.get('population_covered'):,} people" if an.get("population_covered") else "")
    check("analytics reports mean model confidence", an.get("mean_confidence", 0) > 0)
    r = api.get("/analytics/coverage")
    check("per-district coverage roll-up works", r.status_code == 200 and len(r.json().get("districts", [])) == 8)
    r = api.get("/analytics/timeseries", params={"hours": 24})
    check("risk timeseries returns buckets", r.status_code == 200 and "points" in r.json())

    # ------------------------------------------------------------ subscriptions
    r = api.get("/me/subscriptions", headers=C)
    check("a citizen can list their warning subscriptions", r.status_code == 200 and len(r.json()) >= 1)
    r = api.post(f"/me/subscriptions/{wards[1]['code']}", headers=C, params={"channel": "sms", "lang": "gar"})
    check("a citizen can subscribe to another ward", r.status_code == 200)
    r = api.delete(f"/me/subscriptions/{wards[1]['code']}", headers=C)
    check("a citizen can unsubscribe", r.status_code == 200)

    # ---------------------------------------------------------------- sweep
    r = api.post("/risk/sweep", headers=A, params={"broadcast": "true"})
    check("operator sweep runs and reports", r.status_code == 200,
          f"evaluated={r.json().get('evaluated')} created={r.json().get('created')}" if r.status_code == 200 else "")

    return finish(api)


def finish(api: httpx.Client) -> int:
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'-' * 62}")
    print(f"{passed}/{total} checks passed")
    failed = [n for n, ok, _ in results if not ok]
    if failed:
        print("\nFailed:")
        for name in failed:
            print("  -", name)
        return 1
    print("\033[32mAll good.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())

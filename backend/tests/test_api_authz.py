"""Authorisation tests driven through the real ASGI app.

Every case here is a decision the product makes deliberately, and each one is a
way a disaster API gets attacked or misused:

* nobody may re-run the escalation sweep (it can trigger broadcasts);
* only district/system admins may author a warning;
* anyone at all - including an unregistered tourist on the Mussoorie road - may
  file a hazard report, because the report is the signal the model cannot get
  from a satellite;
* and self-registration must never be a way to acquire a role.

Responses are asserted through the same exception handlers the deployment uses,
so a 401/403 here is the real contract, not a dependency-function unit test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import User
from tests.conftest import API, DEMO_PASSWORD

pytestmark = pytest.mark.slow


def alert_body(ward_code: str) -> dict:
    """A draft (broadcast=False) so authoring tests never touch the dispatcher."""
    return {
        "ward_code": ward_code,
        "hazard_type": "landslide",
        "level": "yellow",
        "title": "Manual drill warning",
        "message": "Test copy",
        "broadcast": False,
    }


# --------------------------------------------------------------------------- #
# the sweep is the loudest button on the UI
# --------------------------------------------------------------------------- #
async def test_anonymous_caller_cannot_run_the_risk_sweep(client):
    res = await client.post(f"{API}/risk/sweep")
    assert res.status_code == 401, res.text
    assert res.json()["detail"]


async def test_a_citizen_and_a_responder_cannot_run_the_sweep(client, citizen_headers, field_headers):
    for headers in (citizen_headers, field_headers):
        res = await client.post(f"{API}/risk/sweep", headers=headers, params={"broadcast": False})
        assert res.status_code == 403, res.text


async def test_a_district_admin_sweeps_only_their_own_district(client, admin_headers):
    """Scoping guard: one district's officer must not be able to move the state.

    ``broadcast=False`` still recomputes and persists risk; the clamp is about
    *which wards* are in scope, so it is checked here without messaging anyone.
    """
    res = await client.post(f"{API}/risk/sweep", headers=admin_headers, params={"broadcast": False})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["evaluated"] == 5, "a district_admin is clamped to their own district"
    assert body["telemetry"]["wards"] == 5


async def test_a_district_admin_cannot_sweep_another_district_by_asking(client, admin_headers):
    """An explicit ``district=PKR`` from the DEH collector must be ignored, not honoured."""
    res = await client.post(
        f"{API}/risk/sweep", headers=admin_headers, params={"district": "PKR", "broadcast": False}
    )
    assert res.status_code == 200, res.text
    assert res.json()["evaluated"] == 5


async def test_a_system_admin_can_run_the_sweep_without_broadcasting(client, system_headers):
    res = await client.post(f"{API}/risk/sweep", headers=system_headers, params={"broadcast": False})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["evaluated"] == 40
    assert body["telemetry"]["wards"] == 40
    assert body["telemetry"]["source"] in {"simulated", "open-meteo"}


async def test_a_district_admin_cannot_run_a_scenario_in_another_district(client, admin_headers):
    res = await client.post(
        f"{API}/risk/scenario",
        headers=admin_headers,
        json={
            "ward_code": "PKR-RNK", "rain_1h_mm": 40, "rain_24h_mm": 80,
            "rain_72h_mm": 120, "forecast_6h_mm": 20, "soil_moisture": 0.6,
        },
    )
    assert res.status_code == 403, res.text


async def test_a_system_admin_can_run_a_scoped_sweep(client, system_headers):
    res = await client.post(
        f"{API}/risk/sweep", headers=system_headers, params={"district": "PKR", "broadcast": False}
    )
    assert res.status_code == 200, res.text
    assert res.json()["evaluated"] == 5, "a district filter must actually scope the sweep"


async def test_a_citizen_cannot_broadcast_an_alert(client, citizen_headers):
    res = await client.post(f"{API}/alerts", json=alert_body("DEH-MUS"), headers=citizen_headers)
    assert res.status_code == 403, res.text
    assert "role" in res.json()["detail"].lower()


async def test_a_field_responder_cannot_broadcast_an_alert(client, field_headers):
    res = await client.post(f"{API}/alerts", json=alert_body("PKR-RNK"), headers=field_headers)
    assert res.status_code == 403, res.text


async def test_a_district_admin_can_author_an_alert_for_their_own_ward(client, admin_headers):
    res = await client.post(f"{API}/alerts", json=alert_body("DEH-MUS"), headers=admin_headers)
    assert res.status_code == 201, res.text
    alert = res.json()
    assert alert["level"] == "yellow"
    assert alert["auto_issued"] is False, "manual warnings must be attributable"
    assert alert["status"] == "active"
    assert set(alert["localized"]) == {"en", "hi", "gar"}
    assert alert["advice"]


async def test_a_district_admin_may_not_broadcast_into_another_district(client, admin_headers):
    """Dehradun's collector cannot put Pauri Garhwal under an evacuation order."""
    res = await client.post(f"{API}/alerts", json=alert_body("PKR-RNK"), headers=admin_headers)
    assert res.status_code == 403, res.text
    assert "outside your district" in res.json()["detail"]


async def test_a_system_admin_can_act_across_districts(client, system_headers):
    res = await client.post(f"{API}/alerts", json=alert_body("PKR-RNK"), headers=system_headers)
    assert res.status_code == 201, res.text


# --------------------------------------------------------------------------- #
# crowd reports stay open to anonymous citizens
# --------------------------------------------------------------------------- #
async def test_an_anonymous_visitor_can_file_a_hazard_report(client, ward_lookup):
    ward = await ward_lookup("DEH-LAN")
    res = await client.post(
        f"{API}/reports",
        data={
            "hazard_type": "road_block",
            "title": "Slipped gravel above the bend",
            "description": "One lane covered, two wheeler stuck.",
            "latitude": str(ward["latitude"]),
            "longitude": str(ward["longitude"]),
            "accuracy_m": "12",
            "self_severity": "3",
            "ward_code": ward["code"],
            "lang": "en",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["merged"] is False
    assert body["report"]["status"] == "new"
    assert body["report"]["corroborated_by"] == 1
    assert body["message"].startswith("Report #")
    assert body["confidence"]["value"] >= 0.0


async def test_anonymous_reports_never_leak_a_reporter_identity(client, ward_lookup):
    ward = await ward_lookup("DEH-LAN")
    res = await client.post(
        f"{API}/reports",
        data={
            "hazard_type": "debris_flow",
            "title": "Mud across the culvert",
            "latitude": str(ward["latitude"]),
            "longitude": str(ward["longitude"]),
            "ward_code": ward["code"],
        },
    )
    assert res.status_code == 201, res.text
    report = res.json()["report"]
    assert "reporter_id" not in report
    assert report["reporter_alias"] == "Resident"
    assert report["source"] == "sms", "anonymous traffic is tagged as such"


async def test_corroborating_an_anonymous_report_needs_no_account(client, ward_lookup):
    ward = await ward_lookup("TEH-JKH")
    created = await client.post(
        f"{API}/reports",
        data={
            "hazard_type": "cloudburst",
            "title": "Hail and water on the track",
            "latitude": str(ward["latitude"]),
            "longitude": str(ward["longitude"]),
            "ward_code": ward["code"],
        },
    )
    assert created.status_code == 201, created.text
    code = created.json()["report"]["code"]

    res = await client.post(f"{API}/reports/{code}/corroborate")
    assert res.status_code == 200, res.text
    assert res.json()["corroborated_by"] == 2


async def test_triage_verdicts_need_staff_and_refuse_anonymity(client, citizen_headers, ward_lookup):
    ward = await ward_lookup("TEH-JKH")
    filed = await client.post(
        f"{API}/reports",
        data={
            "hazard_type": "water_logging",
            "title": "Choked drains",
            "latitude": str(ward["latitude"]),
            "longitude": str(ward["longitude"]),
            "ward_code": ward["code"],
        },
    )
    assert filed.status_code == 201, filed.text
    code = filed.json()["report"]["code"]

    anonymous = await client.patch(
        f"{API}/reports/{code}/verdict", json={"status": "confirmed", "note": "looks real"}
    )
    assert anonymous.status_code == 401

    as_citizen = await client.patch(
        f"{API}/reports/{code}/verdict", json={"status": "confirmed"}, headers=citizen_headers
    )
    assert as_citizen.status_code == 403


# --------------------------------------------------------------------------- #
# registration cannot mint privilege
# --------------------------------------------------------------------------- #
async def test_self_registration_ignores_a_privilege_escalation_attempt(client, unique_email):
    res = await client.post(
        f"{API}/auth/register",
        json={
            "full_name": "Wannabe Collector",
            "email": unique_email,
            "password": DEMO_PASSWORD,
            "role": "district_admin",
            "district_code": "DEH",
        },
    )
    assert res.status_code == 201, res.text
    token = res.json()
    assert token["user"]["role"] == "citizen"

    headers = {"Authorization": f"Bearer {token['access_token']}"}
    me = await client.get(f"{API}/auth/me", headers=headers)
    assert me.json()["role"] == "citizen"

    forbidden = await client.post(f"{API}/alerts", json=alert_body("DEH-MUS"), headers=headers)
    assert forbidden.status_code == 403, "a self-registered account must not be able to broadcast"

    users = await client.get(f"{API}/auth/users", headers=headers)
    assert users.status_code == 403


@pytest.mark.parametrize(
    "role",
    ["system_admin", "field_responder", "district_admin", "SUPERUSER"],
)
async def test_every_escalating_role_registration_lands_as_a_citizen_or_is_rejected(
    client, unique_email, role
):
    res = await client.post(
        f"{API}/auth/register",
        json={"full_name": "Escalation Probe", "email": unique_email, "password": DEMO_PASSWORD, "role": role},
    )
    if role == "SUPERUSER":
        assert res.status_code == 422, "an unknown role is a schema error, not a silent downgrade"
    else:
        assert res.status_code == 201, res.text
        assert res.json()["user"]["role"] == "citizen"


async def test_staff_accounts_are_created_by_admins_only(client, admin_headers, unique_email):
    rejected = await client.post(
        f"{API}/auth/staff",
        json={"full_name": "Nope", "email": unique_email, "password": DEMO_PASSWORD, "role": "field_responder"},
    )
    assert rejected.status_code == 401

    created = await client.post(
        f"{API}/auth/staff",
        json={
            "full_name": "Neti Sub-Engineer",
            "email": unique_email,
            "password": DEMO_PASSWORD,
            "role": "field_responder",
            "ward_code": "DEH-KTB",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "field_responder"
    assert created.json()["is_verified"] is True

    # /auth/staff refuses to mint citizens - that path is /auth/register
    silly = await client.post(
        f"{API}/auth/staff",
        json={
            "full_name": "Confused",
            "email": f"citizen-{unique_email}",
            "password": DEMO_PASSWORD,
            "role": "citizen",
        },
        headers=admin_headers,
    )
    assert silly.status_code == 422

    # and the new responder can sign in, but still cannot author a warning
    login = await client.post(
        f"{API}/auth/login", json={"identifier": unique_email, "password": DEMO_PASSWORD}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    alert = await client.post(f"{API}/alerts", json=alert_body("DEH-MUS"), headers=headers)
    assert alert.status_code == 403


# --------------------------------------------------------------------------- #
# credential handling
# --------------------------------------------------------------------------- #
async def test_a_wrong_password_is_401_with_an_indistinguishable_message(client):
    wrong = await client.post(
        f"{API}/auth/login", json={"identifier": "admin.demo@aapaatsathi.in", "password": "Nonsense1!"}
    )
    unknown = await client.post(
        f"{API}/auth/login", json={"identifier": "nobody.demo@aapaatsathi.in", "password": DEMO_PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"], "no user enumeration"


async def test_a_disabled_account_is_refused_at_login_and_mid_session(client, db_session, unique_email):
    register = await client.post(
        f"{API}/auth/register",
        json={"full_name": "Off Duty", "email": unique_email, "password": DEMO_PASSWORD},
    )
    assert register.status_code == 201, register.text
    tokens = register.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert (await client.get(f"{API}/auth/me", headers=headers)).status_code == 200

    user = (await db_session.execute(select(User).where(User.email == unique_email))).scalars().one()
    user.is_active = False
    await db_session.commit()

    login = await client.post(
        f"{API}/auth/login", json={"identifier": unique_email, "password": DEMO_PASSWORD}
    )
    assert login.status_code == 403, login.text
    assert "disabled" in login.json()["detail"].lower()

    # a token issued before deactivation must stop working immediately
    me = await client.get(f"{API}/auth/me", headers=headers)
    assert me.status_code == 403
    sweep = await client.post(f"{API}/risk/sweep", headers=headers, params={"broadcast": False})
    assert sweep.status_code == 403


async def test_a_refresh_token_cannot_be_used_as_an_access_token(client, citizen_tokens):
    headers = {"Authorization": f"Bearer {citizen_tokens['refresh_token']}"}
    res = await client.get(f"{API}/auth/me", headers=headers)
    assert res.status_code == 401, res.text
    assert res.json()["detail"] == "Not authenticated"


async def test_an_access_token_cannot_be_used_where_a_refresh_token_is_required(client, citizen_tokens):
    res = await client.post(f"{API}/auth/refresh", params={"refresh_token": citizen_tokens["access_token"]})
    assert res.status_code == 401, res.text
    assert "refresh" in res.json()["detail"].lower()


async def test_refreshing_with_a_real_refresh_token_works(client, citizen_tokens):
    res = await client.post(f"{API}/auth/refresh", params={"refresh_token": citizen_tokens["refresh_token"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user"]["role"] == "citizen"
    assert body["access_token"] != citizen_tokens["access_token"]
    assert (
        await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    ).status_code == 200


@pytest.mark.parametrize("token", ["garbage", "a.b.c", "x" * 200])
async def test_a_malformed_bearer_token_is_401_not_500(client, token):
    res = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401, res.text


async def test_a_weak_password_is_rejected_before_it_is_ever_hashed(client, unique_email):
    res = await client.post(
        f"{API}/auth/register",
        json={"full_name": "Weak Sauce", "email": unique_email, "password": "password"},
    )
    assert res.status_code == 422, res.text
    assert "digit" in res.json()["detail"]


async def test_duplicate_registration_conflicts_rather_than_overwriting(client, unique_email):
    payload = {"full_name": "First", "email": unique_email, "password": DEMO_PASSWORD}
    first = await client.post(f"{API}/auth/register", json=payload)
    second = await client.post(f"{API}/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


async def test_login_also_accepts_a_phone_identifier(client):
    res = await client.post(
        f"{API}/auth/login", json={"identifier": "+919800000004", "password": DEMO_PASSWORD}
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["role"] == "citizen"


# --------------------------------------------------------------------------- #
# admin-only read surfaces
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path, anonymous, citizen",
    [
        (f"{API}/notifications", 401, 403),
        (f"{API}/notifications/stats", 401, 403),
        (f"{API}/auth/users", 401, 403),
        (f"{API}/analytics/audit", 401, 403),
    ],
)
async def test_operations_surfaces_are_admin_only(client, citizen_headers, path, anonymous, citizen):
    assert (await client.get(path)).status_code == anonymous
    assert (await client.get(path, headers=citizen_headers)).status_code == citizen


@pytest.mark.parametrize(
    "path",
    [
        f"{API}/health",
        f"{API}/meta",
        f"{API}/districts",
        f"{API}/wards",
        f"{API}/risk/overview",
        f"{API}/risk/model",
        f"{API}/alerts",
        f"{API}/reports",
        f"{API}/shelters",
        f"{API}/roads",
        f"{API}/analytics/summary",
    ],
)
async def test_public_reads_do_not_require_an_account(client, path):
    res = await client.get(path)
    assert res.status_code == 200, (path, res.text)

"""Tests for password hashing, JWT issuing and the password policy.

Two non-obvious properties are guarded here:

* the SHA-256 pre-hash, which is the only reason a long passphrase (or a Devanagari
  one, which is multi-byte) does not crash bcrypt at its 72-byte ceiling; and
* the ``typ`` claim, which is what stops a 14-day refresh token being replayed as
  an access token against the admin console.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.core.deps import user_from_token
from app.core.security import (
    ALGORITHM,
    create_token,
    decode_token,
    generate_code,
    hash_password,
    password_problems,
    verify_password,
)
from app.models import Role, User

PASSWORD = "Aapaat@2026"
LONG_PASSWORD = "TrailingEdge" * 20  # 200 characters, 200 bytes ASCII
DEVANAGARI_PASSWORD = "आपतसाथी-2026-सुरक्षित-पासवर्ड"  # >72 bytes when UTF-8 encoded


# --------------------------------------------------------------------------- #
# hashing
# --------------------------------------------------------------------------- #
def test_hash_and_verify_round_trip():
    hashed = hash_password(PASSWORD)
    assert isinstance(hashed, str)
    assert hashed.startswith("$2b$12$"), "rounds=12 is the published work factor"
    assert len(hashed) == 60
    assert PASSWORD not in hashed
    assert verify_password(PASSWORD, hashed) is True


def test_the_same_password_hashes_differently_every_time():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second, "bcrypt must be salting"
    assert verify_password(PASSWORD, first) and verify_password(PASSWORD, second)


def test_a_wrong_password_never_verifies():
    hashed = hash_password(PASSWORD)
    for wrong in ("aapaat@2026", "Aapaat@2027", "Aapaat@2026 ", "", "Aapaat@2026!"):
        assert verify_password(wrong, hashed) is False, wrong


def test_a_password_past_bcrypt_s_72_byte_ceiling_still_works():
    """This is why the sha256 pre-hash exists — and it is easy to regress."""
    assert len(LONG_PASSWORD.encode()) > 72
    hashed = hash_password(LONG_PASSWORD)
    assert verify_password(LONG_PASSWORD, hashed) is True
    assert verify_password(LONG_PASSWORD[:-1], hashed) is False

    # ...whereas handing bcrypt the raw bytes is exactly what raises.
    with pytest.raises(ValueError):
        bcrypt.hashpw(LONG_PASSWORD.encode(), bcrypt.gensalt(rounds=4))


def test_a_multibyte_password_is_measured_in_bytes_not_characters():
    assert len(DEVANAGARI_PASSWORD.encode("utf-8")) > 72
    hashed = hash_password(DEVANAGARI_PASSWORD)
    assert verify_password(DEVANAGARI_PASSWORD, hashed) is True


def test_the_pre_hash_is_sha256_of_utf8_bytes_b64_encoded():
    """Pin the derivation: a change here silently invalidates every stored hash."""
    digest = hashlib.sha256(PASSWORD.encode("utf-8")).digest()
    prepared = base64.b64encode(digest)
    assert len(prepared) == 44
    stored = hash_password(PASSWORD)
    assert bcrypt.checkpw(prepared, stored.encode()) is True


@pytest.mark.parametrize("bad_hash", [None, "", "not-a-bcrypt-hash", "$2b$12$" + "x" * 53])
def test_verify_password_returns_false_instead_of_raising_on_a_mangled_hash(bad_hash):
    assert verify_password(PASSWORD, bad_hash) is False


# --------------------------------------------------------------------------- #
# tokens
# --------------------------------------------------------------------------- #
def test_access_token_round_trip_carries_the_claims_the_gates_read():
    token = create_token(42, role=Role.DISTRICT_ADMIN.value)
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == Role.DISTRICT_ADMIN.value
    assert payload["typ"] == "access"
    assert payload["exp"] > payload["iat"]
    assert len(payload["jti"]) == 16


def test_subjects_are_stringified_so_ints_and_uuids_survive():
    for subject in (7, "7", 999_999):
        assert decode_token(create_token(subject, role="citizen"))["sub"] == str(subject)


def test_extra_claims_are_merged_not_replacing_the_registered_ones():
    token = create_token(3, role="citizen", extra={"ward": "PKR-RNK", "scope": "demo"})
    payload = decode_token(token)
    assert payload["ward"] == "PKR-RNK"
    assert payload["typ"] == "access"  # extras cannot overwrite the type


def test_jti_is_unique_per_issue():
    tokens = {create_token(1, role="citizen") for _ in range(8)}
    assert len({decode_token(t)["jti"] for t in tokens}) == 8


def test_a_refresh_token_is_marked_as_such_and_lives_longer():
    access = decode_token(create_token(5, role="citizen", token_type="access"))
    refresh = decode_token(create_token(5, role="citizen", token_type="refresh"))
    assert refresh["typ"] == "refresh"
    assert access["typ"] != refresh["typ"]
    assert refresh["exp"] > access["exp"]
    assert (refresh["exp"] - refresh["iat"]) // 60 == settings.refresh_token_minutes
    assert (access["exp"] - access["iat"]) // 60 == settings.access_token_minutes


def test_only_the_configured_algorithm_is_accepted():
    token = create_token(9, role="citizen")
    with pytest.raises(jwt.InvalidAlgorithmError):
        jwt.decode(token, settings.secret_key, algorithms=["HS512"])
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token, "a-different-secret-that-is-long-enough-for-hs256", algorithms=[ALGORITHM])


def test_a_tampered_payload_is_rejected():
    token = create_token(9, role="citizen")
    header, body, signature = token.split(".")
    import json

    claims = json.loads(base64.urlsafe_b64decode(body + "=="))
    claims["role"] = Role.SYSTEM_ADMIN.value
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    tampered = f"{header}.{forged}.{signature}"
    with pytest.raises(jwt.PyJWTError):
        decode_token(tampered)


def test_an_expired_token_raises_the_specific_error_the_deps_layer_relays():
    expired = create_token(1, role="citizen", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(expired)
    # a token that expires one minute from now is still valid
    assert decode_token(create_token(1, role="citizen", expires_minutes=1))["sub"] == "1"


def test_a_malformed_token_is_rejected():
    for junk in ("", "abc", "a.b.c", "Bearer " + PASSWORD):
        with pytest.raises(jwt.PyJWTError):
            decode_token(junk)


@pytest.mark.slow
async def test_token_type_is_enforced_where_an_access_token_is_required(db_session):
    """``user_from_token`` is the single gate every dependency funnels through."""
    user = (
        await db_session.execute(select(User).where(User.role == Role.SYSTEM_ADMIN.value))
    ).scalars().first()
    assert user is not None

    access = create_token(user.id, role=user.role, token_type="access")
    refreshed = await user_from_token(access, db_session)
    assert refreshed is not None and refreshed.id == user.id

    for token_type in ("refresh", "password-reset", ""):
        token = create_token(user.id, role=user.role, token_type=token_type)
        with pytest.raises(HTTPException) as exc:
            await user_from_token(token, db_session)
        assert exc.value.status_code == 401

    # the same user *is* accepted with a genuine access token
    assert (await user_from_token(create_token(user.id, role=user.role), db_session)).id == user.id

    with pytest.raises(jwt.PyJWTError):
        decode_token("not-even-close")

    expired = create_token(user.id, role=user.role, expires_minutes=-5)
    with pytest.raises(HTTPException) as exc:
        await user_from_token(expired, db_session)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()

    gone = create_token(999_999, role="citizen")
    with pytest.raises(HTTPException) as exc:
        await user_from_token(gone, db_session)
    assert exc.value.status_code == 403


@pytest.mark.slow
async def test_a_disabled_account_is_refused_even_with_an_unexpired_token(db_session):
    user = (await db_session.execute(select(User).limit(1))).scalars().first()
    token = create_token(user.id, role=user.role)
    original = user.is_active
    user.is_active = False
    await db_session.flush()
    try:
        with pytest.raises(HTTPException) as exc:
            await user_from_token(token, db_session)
        assert exc.value.status_code == 403
        assert "disabled" in exc.value.detail.lower()
    finally:
        user.is_active = original
        await db_session.rollback()


@pytest.mark.slow
async def test_a_missing_token_yields_no_user_rather_than_an_error(db_session):
    assert await user_from_token(None, db_session) is None
    assert await user_from_token("", db_session) is None


# --------------------------------------------------------------------------- #
# password policy
# --------------------------------------------------------------------------- #
def test_the_seeded_demo_password_satisfies_the_policy():
    assert password_problems(PASSWORD) == []


@pytest.mark.parametrize(
    "candidate, expected_substrings",
    [
        ("", ["at least 8 characters", "must contain a letter", "must contain a digit"]),
        ("short1", ["at least 8 characters"]),
        ("longenough", ["must contain a digit"]),
        ("12345678", ["must contain a letter"]),
        ("a1", ["at least 8 characters"]),
        ("A1" + "x" * 130, ["at most 128 characters"]),
    ],
)
def test_password_problems_names_every_failure(candidate, expected_substrings):
    problems = password_problems(candidate)
    assert problems, f"{candidate!r} was accepted"
    joined = "; ".join(problems)
    for expected in expected_substrings:
        assert expected in joined, (candidate, problems)


def test_a_single_character_short_is_not_enough_but_a_letter_plus_digit_is():
    assert password_problems("abc1234")  # 7 characters
    assert password_problems("abcd1234") == []


def test_a_mother_tongue_passphrase_is_accepted():
    """Devanagari letters must satisfy the letter rule.

    This product's users type in Hindi and Garhwali. An ASCII-only ``[A-Za-z]``
    check told a citizen who chose a mother-tongue passphrase that it "must
    contain a letter" and blocked self-registration, even though the SHA-256
    pre-hash below handles the same string fine. Fixed by using a Unicode-aware
    letter class; pinned here so it cannot silently regress.
    """
    assert password_problems("आपतसाथी123") == []
    assert verify_password("आपतसाथी123", hash_password("आपतसाथी123")) is True
    # ...and a purely symbolic password is still rejected.
    assert "must contain a letter" in password_problems("12345678!@#$")


def test_problems_are_human_readable_for_a_form():
    problems = password_problems("x")
    assert all(p.startswith("must") for p in problems)
    assert all(len(p) < 60 for p in problems)


# --------------------------------------------------------------------------- #
# codes
# --------------------------------------------------------------------------- #
def test_generate_code_is_readable_stable_in_shape_and_unique():
    stamp = datetime.now(timezone.utc).strftime("%y%m%d")
    codes = [generate_code("HR") for _ in range(50)]
    assert len(set(codes)) >= 40, "codes must not collide casually"
    for code in codes:
        prefix, date, suffix = code.split("-")
        assert prefix == "HR"
        assert date == stamp
        assert len(suffix) == 4
        assert set(suffix) <= set("0123456789ABCDEF")
    assert generate_code("AL-SMS").startswith("AL-SMS-")


def test_codes_embed_the_utc_date_so_audit_logs_sort():
    code = generate_code("SH")
    today = datetime.now(timezone.utc).date()
    assert code.split("-")[1] == today.strftime("%y%m%d")
    assert (datetime.strptime(code.split("-")[1], "%y%m%d").date() - today) == timedelta(days=0)

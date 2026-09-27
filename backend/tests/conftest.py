"""Shared test fixtures.

Two things are load-bearing here:

1. **The real development database is never touched.** ``app.db`` builds its
   async engine from ``app.config.settings`` *at import time*, so the temp
   SQLite path has to be in the environment before any ``app.*`` module is
   imported. That is why the ``os.environ`` block below sits above the imports
   and why a guard assertion checks the resolved URL.
2. **One event loop for the whole session.** The app uses a module-level async
   engine, whose pooled aiosqlite connections are bound to the loop that opened
   them. pytest-asyncio is therefore configured (see ``pytest.ini``) with
   session-scoped default loop scopes, so every test and fixture shares one loop.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

# --------------------------------------------------------------------------- #
# environment: must happen before importing anything under ``app``
# --------------------------------------------------------------------------- #
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="aapaatsathi-pytest-"))
_TMP_DB = _TMP_ROOT / "test.db"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB.as_posix()}"
os.environ["MEDIA_DIR"] = str(_TMP_ROOT / "media")
os.environ["ENVIRONMENT"] = "test"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["RESET_DATABASE"] = "false"
os.environ["USE_LIVE_WEATHER"] = "false"
os.environ["SMS_PROVIDER"] = "console"
os.environ["SECRET_KEY"] = "test-only-secret-key-not-a-real-one"
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["TWILIO_AUTH_TOKEN"] = ""
os.environ["MSG91_AUTH_KEY"] = ""

from app.config import settings  # noqa: E402
from app.db import SessionLocal, create_schema, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.seed import DEMO_PASSWORD, ensure_seed_data  # noqa: E402

# Guard: if this fails the suite would be writing to the developer's database.
assert _TMP_DB.as_posix() in settings.database_url, (
    f"Tests refuse to run against {settings.database_url!r}; "
    "DATABASE_URL was not applied before app.db was imported."
)
assert "data/aapaatsathi.db" not in settings.database_url, settings.database_url

API = "/api/v1"


# --------------------------------------------------------------------------- #
# session plumbing
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Anyio's own test helper; pinned to asyncio (the app is asyncio-only)."""
    return "asyncio"


@pytest.fixture(scope="session")
def temp_root() -> Path:
    """The throwaway directory holding the test database and uploads."""
    return _TMP_ROOT


@pytest.fixture(scope="session")
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def schema_ready():
    """Create the schema on the temp DB, and dispose the engine afterwards."""
    await create_schema()
    yield
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seeded_db(schema_ready) -> dict[str, int]:
    """One realistic pilot footprint (8 districts / 40 wards / 7 accounts)."""
    async with SessionLocal() as session:
        stats = await ensure_seed_data(session)
        await session.commit()
    assert stats["wards"] == 40, stats
    return stats


@pytest_asyncio.fixture(loop_scope="session", scope="function")
async def db_session(seeded_db):
    """A session for direct service-layer assertions.

    Deliberately *not* rolled back per test: the routers commit internally, so a
    fake isolation layer would only hide behaviour. Tests are written to be
    order-independent instead.
    """
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture(loop_scope="session", scope="function")
async def client(seeded_db):
    """In-process ASGI client — no socket, no second uvicorn on port 8000."""
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30.0
    ) as http:
        yield http


# --------------------------------------------------------------------------- #
# authenticated headers
# --------------------------------------------------------------------------- #
async def login(client: httpx.AsyncClient, identifier: str, password: str = DEMO_PASSWORD) -> dict:
    res = await client.post(f"{API}/auth/login", json={"identifier": identifier, "password": password})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access_token"] and body["refresh_token"]
    return body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="session", scope="function")
async def system_headers(client) -> dict[str, str]:
    """``admin.demo`` — system_admin, can act across districts."""
    return bearer((await login(client, "admin.demo@aapaatsathi.in"))["access_token"])


@pytest_asyncio.fixture(loop_scope="session", scope="function")
async def admin_headers(client) -> dict[str, str]:
    """``collector.demo`` — district_admin for Dehradun (DEH)."""
    return bearer((await login(client, "collector.demo@aapaatsathi.in"))["access_token"])


@pytest_asyncio.fixture(loop_scope="session", scope="function")
async def field_headers(client) -> dict[str, str]:
    """``field.demo`` — field_responder for Pauri Garhwal (PKR)."""
    return bearer((await login(client, "field.demo@aapaatsathi.in"))["access_token"])


@pytest_asyncio.fixture(loop_scope="session", scope="function")
async def citizen_headers(client) -> dict[str, str]:
    """``citizen.demo`` — plain resident of PKR-RNK."""
    return bearer((await login(client, "citizen.demo@aapaatsathi.in"))["access_token"])


@pytest_asyncio.fixture(loop_scope="session", scope="function")
async def citizen_tokens(client) -> dict:
    return await login(client, "citizen.demo@aapaatsathi.in")


@pytest_asyncio.fixture(loop_scope="session", scope="function")
async def admin_tokens(client) -> dict:
    return await login(client, "collector.demo@aapaatsathi.in")


# --------------------------------------------------------------------------- #
# helpers shared by more than one module
# --------------------------------------------------------------------------- #
@pytest.fixture
def unique_email() -> str:
    """A syntactically valid address that cannot collide with a seeded account.

    ``example.test`` is deliberately avoided: email-validator rejects reserved
    special-use TLDs, and ``RegisterIn.email`` is an ``EmailStr``.
    """
    return f"probe-{uuid.uuid4().hex[:10]}@aapaatsathi.in"


@pytest.fixture
def ward_lookup(client):
    """``await ward_lookup("PKR-RNK")`` -> the seeded ward record.

    Tests look coordinates up instead of hard-coding them so the suite keeps
    passing if the seed table is re-cut.
    """

    async def _lookup(code: str) -> dict:
        res = await client.get(f"{API}/wards")
        assert res.status_code == 200, res.text
        for ward in res.json():
            if ward["code"] == code:
                return ward
        raise AssertionError(f"ward {code} missing from seed")

    return _lookup


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Leave no stray databases behind, even if the session was interrupted."""
    for path in sorted(_TMP_ROOT.glob("*")):
        try:
            path.unlink()
        except OSError:
            pass
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)

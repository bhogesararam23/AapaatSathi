"""AapaatSathi API entrypoint.

Run:  ``uvicorn app.main:app --reload``  →  http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.config import settings
from app.core.events import manager
from app.db import SessionLocal, create_schema, drop_schema
from app.models import Ward
from app.seed import ensure_seed_data
from app.services import ingest
from app.services.alerts import run_sweep
from app.services.assembly import all_wards
from app.services.notifier import dispatcher

logging.basicConfig(
    level=logging.INFO if settings.environment == "production" else logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-26s %(message)s",
    datefmt="%H:%M:%S",
)
for noisy in ("httpx", "httpcore", "uvicorn.access"):
    logging.getLogger(noisy).level = logging.WARNING

log = logging.getLogger("aapaatsathi")

DESCRIPTION = """
**AapaatSathi / आपतसाथी** — ward-level landslide and flash-flood early warning for
Uttarakhand's hill districts.

### Why this exists
District-level "red alert" text is useless to the forty families living below a
specific escarpment. This API computes susceptibility per *ward*, fuses
satellite/model rainfall with terrain priors and crowd-corroborated ground
reports, and pushes the result out over SMS and automated voice calls in Hindi,
English and Garhwali — because the households most exposed are the ones least
likely to be holding a smartphone.

### Three surfaces on one API
* **Citizen** — map, live risk, one-tap hazard report, nearest shelter with real
  free-space counts, road status.
* **Field responder** — triage queue, corroborate/confirm/dismiss, road and
  shelter updates.
* **District admin console** — author and broadcast warnings, retune the model,
  run what-if drills, and prove delivery numbers.

### Honesty notes for reviewers
* Default telemetry is a **deterministic simulator**, tagged
  `source='simulated'`; set `USE_LIVE_WEATHER=true` for Open-Meteo.
* Default delivery is the **console provider**, recorded as `simulated`, never
  as sent. Set `SMS_PROVIDER=twilio|msg91` with credentials for real dispatch.
* The risk engine is a **transparent susceptibility prior**, not a trained
  predictor; there is no ward-level labelled event dataset to train on. See
  `GET /api/v1/risk/model`.
"""


# --------------------------------------------------------------------------- #
# background worker
# --------------------------------------------------------------------------- #
async def _monitor_loop() -> None:
    """Periodic telemetry refresh + escalation sweep — the operational heartbeat."""
    while True:
        try:
            await asyncio.sleep(settings.ingest_interval_seconds)
            async with SessionLocal() as session:
                wards = await all_wards(session)
                if not wards:
                    continue
                await ingest.refresh_telemetry(session, wards)
                await session.commit()
                report = await run_sweep(session, wards, auto_broadcast=True)
                await session.commit()
                if report.created:
                    log.info("scheduled sweep escalated %d ward(s)", report.created)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never let a bad tick kill the process
            log.warning("monitor loop error: %s", exc)
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.bind_loop()
    if settings.reset_database:
        log.warning("RESET_DATABASE=true — dropping the existing schema")
        await drop_schema()
    await create_schema()

    async with SessionLocal() as session:
        count = (await session.execute(select(func.count(Ward.id)))).scalar() or 0
        if settings.seed_on_startup and count == 0:
            await ensure_seed_data(session)
            await session.commit()
            wards = await all_wards(session)
            await ingest.refresh_telemetry(session, wards)
            await session.commit()
            await run_sweep(session, wards, auto_broadcast=True)
            await session.commit()
            log.info("seeded %d wards and ran the first sweep", len(wards))

    worker: asyncio.Task | None = None
    if settings.environment != "test":
        worker = asyncio.create_task(_monitor_loop())
    app.state.worker = worker
    log.info(
        "%s v%s ready · db=%s · sms=%s · weather=%s",
        settings.app_name,
        settings.version,
        "sqlite" if settings.is_sqlite else "postgres",
        dispatcher.provider.name,
        "open-meteo" if settings.use_live_weather else "simulated",
    )
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            try:
                await worker
            except (asyncio.CancelledError, Exception):
                pass
        await dispatcher.close()


# --------------------------------------------------------------------------- #
# app
# --------------------------------------------------------------------------- #
app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json",
    contact={"name": "AapaatSathi contributors"},
    license_info={"name": "MIT", "identifier": "MIT"},
    servers=[{"url": "/", "description": "This instance"}],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time"],
)


@app.middleware("http")
async def observability_and_headers(request: Request, call_next):
    """Request timing plus the boring security headers a public-tool review asks for."""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.perf_counter() - start) * 1000:.2f}"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(self), microphone=()")
    if settings.environment == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Flatten Pydantic errors into something a form on a phone can display."""
    fields: dict[str, str] = {}
    for item in exc.errors():
        loc = ".".join(str(p) for p in item.get("loc", ()) if p not in {"body", "query", "form"})
        fields[loc or "request"] = item.get("msg", "invalid")
    return JSONResponse(
        status_code=422,
        content={"detail": "Check the highlighted fields", "fields": fields},
    )


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log the traceback, return a correlation id — never leak internals to a
    screen someone is projecting to a room of officials."""
    import uuid

    ref = uuid.uuid4().hex[:8]
    log.exception("unhandled error %s on %s %s", ref, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal error", "ref": ref, "message": f"Quote reference {ref} when reporting this."},
    )


app.include_router(api_router, prefix="/api/v1")

# Uploaded hazard photos. Served from the data dir; nothing else is exposed.
app.mount("/api/v1/media", StaticFiles(directory=settings.media_dir), name="media")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, Any]:
    return {
        "name": "AapaatSathi",
        "tagline": settings.app_tagline,
        "version": settings.version,
        "docs": "/docs",
        "api": "/api/v1",
        "health": "/api/v1/health",
        "status": "ok",
    }


@app.get("/favicon.ico", include_in_schema=False, response_model=None)
async def favicon() -> FileResponse | JSONResponse:
    from pathlib import Path

    candidate = Path(settings.media_dir).parent / "favicon.ico"
    if candidate.exists():
        return FileResponse(candidate)
    return JSONResponse(status_code=204, content=None)

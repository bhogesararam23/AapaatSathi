# Architecture

AapaatSathi is a ward-level landslide and flash-flood early-warning system for
Uttarakhand's hill districts. Two packages, one contract:

```
┌────────────────────┐   REST /api/v1   ┌──────────────────────────┐
│  frontend/         │ ◄──────────────► │  backend/                │
│  React 18 + TS     │   WebSocket /ws  │  FastAPI + SQLAlchemy    │
│  Vite + Tailwind   │                  │  async, Pydantic v2      │
│  MapLibre GL       │                  │                          │
└────────────────────┘                  └─────────┬────────────────┘
                                                  │
                                        ┌─────────▼─────────┐
                                        │ SQLite (dev)       │
                                        │ Postgres (deploy)  │
                                        └────────────────────┘
                                                  ▲
                              ┌───────────────────┼───────────────────┐
                              │                   │                   │
                     Open-Meteo rainfall   Terrain priors      Resident reports
                     (optional, live)      (SRTM / GSI /       (app, SMS, IVR)
                                           NDVI — seeded)
```

## Request and data flow

1. **Telemetry in.** `services/ingest.py` writes one `telemetry_readings` row per
   ward gauge. Either Open-Meteo (when `USE_LIVE_WEATHER=true`) or a
   deterministic monsoon simulator. Every row carries a `source` tag:
   `simulated`, `open-meteo`, or `scenario`. Nothing downstream ever infers
   "real" from absence of a tag.
2. **Scoring.** `services/risk_engine.py` reduces ten factors — four dynamic
   (rain intensity, 72 h antecedent, soil saturation, 6 h forecast), six static
   (slope, lithology, thrust proximity, channel proximity, NDVI deficit, event
   history) — into a 0–100 susceptibility score. Each factor is a piecewise
   interpolation clamped to `[0,1]`, multiplied by a published weight that sums
   to 1.0.
3. **Crowd overlay.** Corroborated resident reports apply a multiplier bounded
   by `CROWD_UPLIFT_CAP` (default 1.25).
4. **Persistence.** `ward_risks` is append-only and stores the full per-factor
   breakdown as JSON. Any warning can therefore be replayed and defended later.
5. **Escalation.** `services/alerts.py::run_sweep` snapshots each ward's prior
   level **before** writing new scores, then fires only on a real upward
   transition past the yellow line, with a dedupe window. Comparing after the
   write would make every escalation look like a no-op.
6. **Delivery.** `services/notifier.py` resolves recipients from subscriptions,
   renders the message in each recipient's own language, and dispatches through
   a provider adapter. Each attempt is a `notifications` row with a status of
   `sent`, `simulated`, `queued` or `failed`.
7. **Fan-out.** Every state change publishes on the in-process bus
   (`core/events.py`) and reaches connected WebSocket clients. `public` carries
   anonymised scores only; `ops` requires a staff token.

## Layout

```
backend/app/
  config.py            pydantic-settings; every knob is an env var
  db.py                async engine, session factory, Base
  models.py            all ORM models (see design notes at the top of the file)
  schemas.py           Pydantic request/response contracts
  seed.py              8 districts / 40 wards / gauges / shelters / roads
  core/
    security.py        bcrypt + JWT
    deps.py            auth and role gates as Annotated[...] aliases
    events.py          WebSocket hub with replay buffer
  services/
    risk_engine.py     the scoring model
    alerts.py          escalation, authoring, broadcast
    notifier.py        provider adapters + dispatcher + ledger
    ingest.py          telemetry acquisition and simulation
    assembly.py        read-model composition shared by API and tests
    geo.py             haversine, polygon containment, bearing
    i18n.py            en / hi / gar message catalog
  api/routes/          auth, geo, risk, alerts, reports, assets, ops, live
frontend/src/
  api/                 typed client + hand-written response types
  components/          ui primitives, RiskMap, briefing panels, Layout
  pages/               Home, Ward, Report, Shelters, Roads, Model,
                       SignIn, Responder, Console
  state/               session (JWT) and live (WebSocket) providers
  hooks.ts             useAsync, useGeolocate, useNow, useLocalState
```

## Deliberate decisions

Recorded in full under [`adr/`](adr/):

- **A note on the model:** transparent additive scoring, not machine learning.
- **A note on the database:** SQLAlchemy async on SQLite by default, Postgres by
  configuration, and no PostGIS.
- **A note on delivery:** pluggable providers with a simulated default, and a
  ledger that never calls a simulated send a real one.

## Security posture

- Passwords: bcrypt with SHA-256 pre-hash (handles passphrases past bcrypt's
  72-byte limit).
- Tokens: short-lived access JWT plus a refresh token; `typ` is validated so a
  refresh token cannot be used as a bearer credential.
- Roles: `citizen`, `field_responder`, `district_admin`, `system_admin`.
  Self-registration **always** produces a citizen regardless of the payload;
  staff accounts are created by an admin. District admins are scoped to their
  own district on alert and ward operations.
- Privacy: reporter identity is never serialized on public hazard feeds; phone
  numbers are masked in the notifications list; the public WebSocket channel
  carries no personally identifying data; IVR is only attempted at orange/red.
- Failure modes: a 500 returns a correlation id and logs the traceback
  server-side rather than leaking internals into a UI someone may be projecting.

## Known limits, stated plainly

- Terrain, population and asset figures are realistic approximations for
  demonstration. They must be replaced with GSI / Survey of India / State DGRRM
  layers before any operational use.
- No field validation has been performed and no accuracy claim is made.
- The system degrades to "no warning" if the network, the SMS gateway or the
  power are down — which is precisely why the paper-and-siren chain at the
  village level has to stay in front of it, not behind it.

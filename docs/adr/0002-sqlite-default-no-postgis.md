# ADR 0002 — SQLite by default, Postgres by configuration, no PostGIS

**Status:** accepted
**Date:** 2026-09-27

## Context

The reviewer of an open-source civic-tech project clones the repo and runs one
command. If that requires Docker, a Postgres role, a PostGIS extension and a
`.env` they do not have, most reviews never happen. The same is true of a
district control room running a demo on a government laptop with no admin
rights.

At the same time, a real deployment needs a real database, and geospatial work
usually means PostGIS.

## Decision

Use SQLAlchemy 2.x async with the URL as the only switch:

- default `sqlite+aiosqlite:///./data/aapaatsathi.db`
- production `postgresql+psycopg://…` via `DATABASE_URL`

Avoid PostGIS. Store ward polygons as JSON rings and compute distance,
containment and bearing in `services/geo.py` with spherical formulas.

## Consequences

**Positive**

- `uvicorn app.main:app` works with zero setup, on Windows, macOS and Linux.
- CI does not need a database service container.
- The same code path runs on a laptop and on managed Postgres (Neon, Supabase,
  RDS) with no branch in the application.
- Hill-district wards are 1–2 km across; haversine and ray casting are accurate
  far beyond the precision the product needs.

**Negative**

- No spatial index. Ward-count scale is dozens to low thousands, so a linear
  scan is fine; at tens of thousands of polygons it would not be.
- SQLite has no real concurrency for writes; a multi-district deployment must
  use Postgres.
- JSON polygons are larger than binary geometry over the wire — mitigated by
  the single `/geo/choropleth` call rather than per-ward fetches.

## When to revisit

Replace `geo.py` with PostGIS `geography` columns and a GiST index once the
ward count passes roughly 5,000, or as soon as the system consumes official
revenue-village boundaries instead of the generated blobs in `seed.py`. The
interface is narrow enough that this is a one-module swap.

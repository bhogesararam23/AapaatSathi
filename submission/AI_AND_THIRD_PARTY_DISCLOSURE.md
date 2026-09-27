# AI Assistance & Third-Party Disclosure

**AapaatSathi — Elite Coders CodeSprint 2026**
Required by Rule 1 (disclose pre-existing code, components, libraries, APIs, datasets and materials) and Rule 4 (AI-assisted tools permitted).

This document exists so that a judge, a mentor, a journalist or an inquiry committee can reconstruct exactly which parts of AapaatSathi are our own work, which are third-party, which are machine-assisted, and which numbers are modelled rather than measured. Nothing below is a formality: the material claims are in Section 4 and Section 5, and they are the claims we would least like to be caught overstating.

> **Two documents referenced below are repo artefacts we still owe, not files that exist today:** `LICENSE` (MIT, to be added with the public repository) and `ASSISTED_WORKLOG.md` (file-level record of machine-generated code). Both are tracked as blocking items in `TEAM-AND-TASKS.md`, and this document will name their final paths once they are committed. We are flagging them here rather than writing as if they were already in place.

---

## 1. Origin of the work

| Question | Answer |
|---|---|
| Was the project created specifically for CodeSprint 2026? | Yes. The idea, architecture, data model, risk engine, alert pipeline, delivery layer, localisation and console were all produced during this challenge. |
| Is any pre-existing project, codebase, product or fork included? | No. No pre-existing code of ours or of anyone else was imported as a starting point. |
| Were any pre-existing datasets used? | No ward-level Uttarakhand event dataset exists to use. All figures are approximations we assembled — see Section 4. |
| Who wrote it? | Two team members, with AI assistance as described in Section 2. Both are students; neither is affiliated with a company or professional organisation. |
| Who owns it? | We do (Rule 9), subject to the third-party licences in Section 3. |

## 2. AI tools used

AI-assisted development tools were used, as Rule 4 permits. Stated specifically rather than generically:

| Tool | Role in development | What it did **not** do |
|---|---|---|
| **Qoder** (agentic AI coding assistant, `qoder.com`) | Primary implementation partner. Generated and edited substantial portions of the FastAPI backend (models, routers, services, seed module) and the React/TypeScript console from our specifications; ran the smoke test and cold-boot verification; assisted with refactors and docstrings. | Did not choose the problem, the domain approach, the ten risk factors, their weights, the crowd-uplift cap, the escalation-on-transition rule, the simulated-versus-sent ledger design, the seed locations or the disclosure policy. Those are ours, and we can defend each in the pitch. |
| **ChatGPT** (OpenAI) | Background research on Himalayan landslide controls, lithology susceptibility, cloudburst thresholds, and the wording of public-safety messaging; sanity-checking disaster timelines and casualty figures for the named events. | Produced no code that shipped, and no risk weight. It did not, and cannot, validate anything numerically — every factual figure quoted in our submission is cross-checked against a real source by us, and every modelled value is marked as modelled. |
| **Editor/tooling AI** (TypeScript language service, ESLint autofix, Vite, Prettier formatting) | Mechanical: type-checking, lint autofix, formatting. | No design decisions. |

**Responsibility.** Under Rule 4, participants remain responsible for the submission. We accept that responsibility for AI-generated lines exactly as for hand-written ones: every file in the repository has been read and reviewed by us, and where we cannot explain a line we removed it rather than kept it. AI output was treated as a draft to be verified, never as an authority. Two specific corrections came out of that discipline: the seed module's non-deterministic hashing (replaced with a stable checksum so documented example codes stay valid across boots) and the async ORM loading strategy (`selectin` with no back-references, to avoid `MissingGreenlet` failures under load).

**Assisted work is disclosed at file level** in `ASSISTED_WORKLOG.md` (to be committed with the public repository — see the note at the top of this document), listing the modules where machine-generated code constitutes the majority of lines. We did not adopt a "human-wrote-the-important-parts" framing, because it is unfalsifiable and we did not want to be asked to defend it.

## 3. Third-party libraries, frameworks, APIs and services

All are used under their own licences (Rule 5), with version ranges declared in `backend/requirements.txt`, `backend/requirements-postgres.txt` and `frontend/package.json`. Licences were read from each installed package's own metadata rather than assumed. One dependency is weakly copyleft — `certifi` is MPL-2.0, whose obligations attach to that file only and are satisfied by using it unmodified — and no GPL or AGPL component is present, so MIT licensing of our code is unimpaired.

### 3.1 Backend runtime dependencies

| Package | Licence | Used for | Ours? |
|---|---|---|---|
| FastAPI 0.115+ | MIT | Web framework, dependency injection, OpenAPI | No |
| Starlette | BSD-3 | ASGI layer under FastAPI | No |
| Uvicorn[standard] | BSD-3 | ASGI server | No |
| SQLAlchemy 2.0.30+ | MIT | Async ORM | No |
| aiosqlite | MIT | Async SQLite driver (default database) | No |
| greenlet | MIT / PSF-2.0 | Coroutine support required by SQLAlchemy async | No |
| Pydantic v2 / pydantic-core / pydantic-settings | MIT | Validation, settings from environment | No |
| PyJWT | MIT | Access/refresh tokens | No |
| bcrypt | Apache-2.0 | Password hashing (SHA-256 pre-hash, cost 12) | No |
| python-multipart | Apache-2.0 | Multipart form and photo upload | No |
| httpx | BSD-3 | Outbound calls to Open-Meteo, Twilio, MSG91 | No |
| websockets | BSD-3 | WebSocket transport | No |
| python-dotenv | BSD-3 | `.env` loading | No |
| email-validator | Unlicense (public domain) | Email field validation | No |
| psycopg[binary] (optional, `requirements-postgres.txt`) | PostgreSQL Licence | Postgres driver when `DATABASE_URL` is set | No |

Transitive dependencies (anyio, h11, httpcore, certifi, click, idna, plus build/test tooling) resolve automatically from those declarations; their licences are MIT, BSD-2/3, Apache-2.0, ISC, PSF-2.0 and MPL-2.0, and a generated notice file will be committed alongside `LICENSE`.

### 3.2 Frontend dependencies

| Package | Version in use | Licence |
|---|---|---|
| react / react-dom | 18.3.1 | MIT |
| react-router-dom | 6.30 | MIT |
| maplibre-gl | 4.7.1 | BSD-3-Clause |
| recharts | 2.15 | MIT |
| i18next / react-i18next | 23.16 / 15.7 | MIT |
| lucide-react | 0.445 | ISC |
| clsx | 2.1 | MIT |
| date-fns | 3.6 | MIT |
| typescript (dev) | 5.9 | Apache-2.0 |
| vite (dev) / @vitejs/plugin-react (dev) | 5.4 / 4.7 | MIT |
| tailwindcss / postcss / autoprefixer (dev) | 3.4 / 8.5 / 10.6 | MIT |
| eslint (dev) | 8.57 | MIT |

### 3.3 External services and APIs

| Service | How used | Licence / terms | Cost | Status |
|---|---|---|---|---|
| **Open-Meteo Forecast API** (`api.open-meteo.com/v1/forecast`) | Bulk observed (3 past days) and forecast (1 day) hourly precipitation per ward centroid when `USE_LIVE_WEATHER=true`. Falls back to the local simulator on any transport failure. | Free for **non-commercial** use; underlying ECMWF/COPERNICUS data is CC-BY 4.0 — attribution required if the live path is used publicly. | Free tier | **Disabled by default.** No key required. Not stress-tested at monsoon scale. |
| **MapLibre demo tiles** (`demotiles.maplibre.org` glyph endpoint) | Font glyph glyphs for the basemap style in development. | MapLibre demo service, provided as-is | Free | **Must be replaced** with a self-hosted or licensed tile/glyph endpoint before any public or operational deployment. Flagged as a known issue. |
| **Twilio REST API** | SMS (`/Messages.json`) and voice IVR (`/Calls.json` with TwiML `<Say>`) adapters. | Commercial; usage-billed | Paid | Implemented, **not exercised at scale**, credentials not committed. IVR currently emits `language='en-IN'` only. Contains a placeholder `StatusCallback` URL (`example.invalid`) that must be replaced with a real delivery-report endpoint before production. |
| **MSG91** | Bulk SMS adapter (`api.msg91.com/api/v2/sendsms`), chosen because it is the common route for Indian government bulk-SMS arrangements. | Commercial; DLT-regulated in India | Paid | SMS implemented. **IVR deliberately unimplemented**: it returns a failure with an explanatory error rather than pretending to succeed, because voice campaigns need a registered template ID we do not hold. |

No credentials, API keys, phone numbers of real residents, or production connection strings are present anywhere in the repository. `.env` is git-ignored; `.env.example` documents every variable.

### 3.4 Reference material consulted

Published literature on Himalayan landslide susceptibility (slope-angle thresholds, Siwalik and Lesser Himalayan lithological behaviour, antecedent-rainfall triggers, NDVI/root-cohesion relationships) informed the **shape** of the factor curves and the **relative ordering** of the weights. Publicly reported timelines of the 2021 Chamoli disaster, the August 2021 Ranikhot slide, the October 2021 Kalingjadh flood at Dharali and Silyari, the 2023 Kirartoli cloudburst, and the recurring Chhilbikhuna slide zone informed the **choice of pilot wards**. These informed design; they were not ingested as data, and no paper's numbers are reproduced as ours.

## 4. Model disclosure — the most important section

**The risk weights are hand-set heuristics. They are not fitted to a labelled dataset, and no accuracy metric exists.**

Why not: Uttarakhand has thousands of recorded slope failures but **no ward-level, temporally aligned feature-plus-outcome ledger** — no dataset pairs each event with the antecedent rainfall, soil state and telemetry that preceded it at ward resolution. Any model "trained" on available records would be fitted to a truncated, non-aligned sample and its reported accuracy would be an artefact of that fitting. Presenting such a number to a judge, or to a district magistrate, would be dishonest. We would rather show a prior we can defend term by term.

Specifically:

- **Ten factors, weights summing to exactly 1.0** (`DEFAULT_WEIGHTS`, `backend/app/services/risk_engine.py`, published live at `GET /api/v1/risk/model` as `weights_sum`). Weights were set from the relative influence each control has in published Himalayan susceptibility work, then adjusted for what the MVP can actually observe. They are opinion, labelled as opinion.
- **Piecewise-normalised curves** (`SLOPE_CURVE`, `RAIN_1H_CURVE`, `RAIN_72H_CURVE`, `FORECAST_6H_CURVE`, `FAULT_KM_CURVE`, `RIVER_KM_CURVE`) are hand-plotted from heuristics, then linearly interpolated and clamped. The slope susceptibility peak in the 30–45° band, the Siwalik-dominant lithology ordering, and the NDVI baseline of 0.75 for healthy mid-elevation forest are our chosen constants, not measured ones.
- **`probability_24h`** is a logistic transform of the score centred on the orange threshold. It is **not** a calibrated probability of failure; it is an ordering device so that a red ward reads as more urgent than an orange one. Labelled as such in the API.
- **`EXPOSURE_FRACTION`** (2 / 12 / 35 / 70 percent of ward population at blue / yellow / orange / red) is a conservative hand-set mapping used to compute "people exposed" rather than assert it.
- **`_confidence`** is a hand-weighted additive index of data availability, not statistical confidence.
- **The crowd-uplift cap of 1.25** and its internal sub-weights (corroboration 0.30, confirmed reports 0.45, open reports 0.15, scaled by reporter trust) are a deliberately bounded design choice, not a fitted parameter.
- **Model version is `as-risk-1.2`**, persisted alongside every score and every alert, so a later run under different weights cannot be confused with an earlier one.

The API states this itself, so the disclaimer travels with the data rather than living only in our README:

> "Susceptibility prior, not a prediction of a specific slope failure. Weights encode published Himalayan landslide heuristics and local terrain priors; they are not fitted against a labelled event dataset, because no ward-level, time-aligned Uttarakhand event ledger exists."

**What would change this:** access to a state disaster ledger (State DGRRM / NDRF / district incident records) with event timestamps and locations. Our planned calibration protocol and the published precision/recall that would follow are in Section 7. Until then, orange and red mean "act now" and yellow means "prepare" — not a probability.

## 5. Data disclosure — what is real and what is modelled

| Data | Provenance | Real or modelled? |
|---|---|---|
| District names, codes, headquarters, approximate area and population (8 districts) | Public Census-of-India-scale figures for the named districts | Real locations; **population rounded** |
| Ward names and coordinates (40 wards) | Real settlements in the named districts, including Ranikhot, Dharali, Silyara, Karnaprayag, Chhilbikhuna, Phata, Kund, Devprayag, Naya Tehri, Mussoorie/Lalmati Tibba | **Real places at approximate coordinates.** Ward polygons are synthetic hexoid outlines generated deterministically around each centroid — they are *not* surveyed revenue boundaries |
| Slope angle, elevation, aspect, lithology class, distance to thrust zone, distance to channel, NDVI, historical event count | Our plausible engineering approximations for each named location, informed by published Himalayan terrain behaviour | **Modelled. Not surveyed, not remote-sensed, not derived from an actual DEM in this build.** This is the single largest gap to close |
| Population, households, children, elderly, disabled, schools, health centres, registered phones, connectivity class | Census-scale derivation from settlement size (`households = population / 3.7`, `children = 15.5%`, `elderly = 12.1%`, `disabled = 3.1%`, phone penetration 42/58/68 percent by connectivity band), then rounded | **Modelled for the purpose of computing exposure rather than asserting it.** Not official figures |
| Rain gauges (51) | Seeded as assets at plausible offsets from ward centroids | **Modelled inventory.** No physical sensor is integrated |
| Shelters (18), road segments (18), resource units (12) | Real settlement and highway references (NH-73 Bhaironghat ghat, NH-7 Devprayag–Kodori, NH-107 Guptkashi–Phata, Kausani–Jaint) with plausible capacities, personnel and statuses | **Real road names; modelled attributes.** Shelter occupancy is deterministically derived from a checksum of the name |
| Telemetry (rainfall, soil moisture, river stage) | **Deterministic simulator** by default — monthly Garhwal/Kumaon monsoon baseline × diurnal convective cycle × elevation factor × a SHA-256 hash of `(ward_code, hour_bucket)`, with heavy-tailed bursts. River stage is a simple rating curve on accumulation. | **Simulated.** Every row is written with `source='simulated'`. Scenario injections carry `source='scenario'`. Only the Open-Meteo path writes `source='open-meteo'`, and it is off by default |
| Hazard reports (11 seeded) | Written by us as realistic example incidents in the voice of residents (including "Kalingjadh sound like a train again") | **Fictional demonstration content.** No real resident has filed a report |
| User accounts (7 demo), subscriptions (7) | Fictional named personas; password `Aapaat@2026`; phone numbers in the reserved `+9198000000xx` demo range | **Fictional.** No real personal data is present anywhere in the repository |
| District office / collector phone numbers, shelter manager names and phone numbers | **Synthesised** in `seed.py` from a counter and a checksum of the shelter name; they imitate the format of real Uttarakhand numbers and must not be dialled | **Fabricated placeholders.** Deliberately not the real numbers of any collector, shelter officer or unit |
| Delivery ledger (~2,200 messages in a demo run, 2,170 SMS / 63 IVR; Garhwali 1,506 / Hindi 726 / English 1) | Generated by the **console provider**, which logs and records without network contact | **`simulated`, never `sent`.** No real message has ever been delivered to a real resident by this system |

The `DISCLAIMER` constant at the top of `backend/app/seed.py` carries this in-repo:

> "Terrain, population and asset figures are realistic approximations assembled for a working MVP demonstration. They are NOT surveyed field data and MUST be replaced with GSI / Survey of India / State DGRRM layers before any operational use."

### 5.1 Synthetic recipients — stated explicitly

`resolve_recipients()` addresses registered subscribers for real, and then represents the ward's remaining registered-phone population as **deterministically generated synthetic numbers**, capped at 60 per ward per run, so that reach and shelter planning have a denominator. These are written to the ledger as `simulated`. The API separates `real_recipients` from `estimated_reach` in `POST /api/v1/alerts/preview` rather than blending them. No real phone number has been imported, stored or messaged.

### 5.2 What we deliberately did not build

No scraping of resident data. No integration with any government system. No claim of partnership with SDMA, State DGRRM, NDRF, IMD or any district administration — the names appearing in seed data (NDRF battalions, ITBP camps, control-room number 1070, 112) are public emergency information and realistic context, **not endorsements or agreements**. Nothing has been deployed. Nobody has signed off on anything.

## 6. Verification performed

| Check | Result |
|---|---|
| Cold boot from an empty database with zero configuration | Passes. Creates the SQLite schema, seeds 8 districts / 40 wards / 51 gauges / 18 shelters / 18 road segments / 12 resource units / 11 reports / 7 accounts, generates telemetry, runs the first escalation sweep, starts the monitor loop |
| `backend/scripts/smoke_test.py` end-to-end against that cold-booted instance | **60 / 60 checks passed** (27 September 2026, local Windows, SQLite + console provider). Covers role boundaries, anonymous reporting, corroboration merging, three-language preview, scenario escalation, physically impossible scenario rejection, alert authoring and revocation, ledger labelling, shelter and road updates, analytics roll-ups and subscriptions |
| Weight sum | `GET /api/v1/risk/model` returns `weights_sum = 1.0` |
| Factor explainability | Every scored ward returns exactly 10 factors, each with a non-zero weight and a written rationale; breakdown persisted to `ward_risks.factors` |
| Uplift cap | Verified: a single low-trust report yields 1.039; three corroborated plus a confirmed report hits the 1.25 ceiling; ten confirmed reports also return 1.25 |
| Escalation-on-transition | Verified: three corroborated reports moved ward RPR-KND from yellow 58.41 to orange 65.41; the next sweep auto-issued one alert (`from: yellow, to: orange`) and wrote an `alert.auto_issued` audit entry; an immediate repeat sweep returned `created = 0` |
| Determinism | The simulator hashes `(ward_code, hour_bucket)`, so two runs at the same wall-clock hour produce identical hyetographs; `zlib.crc32` is used for stable code generation because Python's `hash()` is per-process randomised |
| Live weather path | Open-Meteo adapter implemented; **not** load-tested. On any failure it logs a warning and falls back to the simulator rather than erroring |
| Real SMS path | **Not verified.** Twilio and MSG91 adapters are real REST implementations but no live dispatch has been performed, because no real resident numbers exist in the system |
| Test suite | `backend/tests/` (pytest) and `scripts/smoke_test.py` are the verification surface. Coverage is functional and end-to-end rather than unit-level; a gap we acknowledge rather than paper over |

## 7. Commitments before any operational use

1. Replace every modelled terrain and population value with authoritative layers: **GSI** National Geomorphoscape / landslide-susceptibility maps, **Survey of India** toposheets and official ward boundaries, **Census** ward-level population and asset counts, **State DGRRM / NDRF** historical event records, and **SRTM or CartDEM 30 m** derived slope, plus **Sentinel-2** NDVI. Publish the derived grids under the same licence as the code.
2. Calibrate weights and thresholds against a back-tested event ledger with held-out seasons, then publish precision and recall per level and the false-alarm rate. If calibration is not possible with available data, say so publicly rather than publishing a number.
3. Field-validate with one block administration, on recorded and human-reviewed Hindi and Garhwali voice scripts, with a documented opt-in, data-retention and deletion policy for resident phone numbers, and a named nodal officer accountable for the alert channel.
4. Replace MapLibre demo tiles with a properly licensed or self-hosted basemap; replace the placeholder Twilio `StatusCallback`; add delivery-receipt handling so `sent` becomes `delivered`.
5. Have the risk engine reviewed by someone with geotechnical or hazard-domain credentials before it warns anyone.

## 8. Contact and correction policy

If any statement here is inaccurate, or if a judge or reviewer identifies an undisclosed third-party component or an overstated claim, tell us and we will correct the document and the submission immediately. We would rather lose on a correction than win on an overstatement — a system that eventually carries evacuation orders for real villages cannot be built on numbers we cannot defend.

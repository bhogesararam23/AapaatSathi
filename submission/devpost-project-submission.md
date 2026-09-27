# AapaatSathi — Devpost Project Submission

**Elite Coders CodeSprint 2026**

| | |
|---|---|
| Project | AapaatSathi (आपतसाथी) — ward-level landslide & flash-flood early warning |
| Team | 2 members: [name 1], [name 2] |
| Try it live | [deployed URL] |
| Source | [public GitHub repo URL] — MIT |
| Demo video | [video URL] |
| API docs | [deployed URL]/docs |
| Built with | FastAPI, SQLAlchemy 2 (async), Pydantic v2, React 18, TypeScript, Vite, Tailwind, MapLibre GL |

> Bracketed slots are the only items to fill in before clicking submit on 15 November. Everything else in this document describes code that exists in the repository.

---

## 1. Overview

AapaatSathi is an early-warning and response-coordination system for landslide and flash-flood risk in Uttarakhand's hill districts. It scores risk per **ward** — the smallest administrative unit with a population and a coordinate — rather than per district, and delivers warnings by **SMS and automated voice call** in **English, Hindi and Garhwali**.

It has three surfaces on one API: a **citizen** view (live risk, one-tap hazard reporting, nearest shelter, road status), a **field responder** view (triage queue, corroboration, asset updates), and a **district admin** console (author and broadcast warnings, retune the model, run drills, audit delivery).

The design premise is that a warning system in the Himalaya fails for two specific reasons — the alert is too coarse to act on, and it arrives on a channel the most exposed households do not have. AapaatSathi addresses both, and keeps an audit trail because systems that warn about death get investigated.

## 2. The problem

Himachal and Uttarakhand sit on geologically young, actively thrusting mountains with monsoon rainfall concentrated into a few weeks. Slope failure is not rare; it is seasonal and it is local.

Named events in the pilot footprint:

| When | Where | What happened |
|---|---|---|
| Aug 2021 | Ranikhot, NH-73, Pauri Garhwal | Slope failure killed roughly fifty people, most of them pilgrims assembled below the slide — the deadliest Uttarakhand landslide in recent years |
| Oct 2021 | Dharali & Silyari, Uttarkashi | Debris-laden flash flood on the Kalingjadh destroyed the Dharali market; Silyara was scoured in the same event |
| Feb 2021 | Karnaprayag, Chamoli | The Chamoli debris avalanche sent a flood wave past the town and destroyed two hydropower projects |
| Jul 2023 | Jakholi block, Tehri | Kirartoli cloudburst and Mandakini flooding originated in this block |
| Every monsoon | Chhilbikhuna, Almora | Recurring slope failure on the Almora–Pithoragarh road; a textbook slow-motion slide zone |

Two structural gaps turn these into preventable deaths:

1. **Scale mismatch.** District-level red alerts are simultaneously correct and useless. A hill ward is a few hundred metres across; a district is thousands of square kilometres. The forty families in a runout zone cannot act on an instruction addressed to a million people.
2. **Channel mismatch.** The households most exposed to slope failure — lower slopes, riverbanks, older settlements — are the least likely to hold a charged smartphone with mobile data. An app-based warning reaches the people already safest.

## 3. The solution

**A transparent susceptibility model.** Ten piecewise-normalised factors, each in [0, 1], each with a published weight that sums to 1.0, combined additively into a 0–100 score mapped to five levels (green / blue / yellow / orange / red at 25 / 45 / 62 / 76).

| Factor | Weight | Why it is there |
|---|---|---|
| Rainfall intensity (last hour) | 0.16 | Short-burst rate — the cloudburst trigger |
| Slope angle | 0.14 | Dominant terrain control; peaks in the 30–45° band |
| Antecedent rainfall (72 h) | 0.12 | Saturated ground fails at far lower intensity |
| Forecast rainfall (next 6 h) | 0.12 | The only forward-looking term; lets warnings lead events |
| Soil saturation | 0.10 | Pore-pressure proxy |
| Lithology | 0.10 | Siwalik and sheared Lesser Himalayan units fail most |
| Recorded past events | 0.07 | A slope that moved before will move again (log-scaled) |
| Thrust-zone proximity | 0.06 | Jointing around MBT/MCT creates planes of weakness |
| Channel proximity & stage | 0.08 | Toe erosion removes slope support |
| Vegetation / root-cohesion deficit | 0.05 | NDVI against a healthy 0.75 baseline |

Every evaluation **persists the full per-factor breakdown** (observed value, normalised value, weight, contribution, plain-language rationale) into `ward_risks.factors`. Any historical score can be reopened and defended term by term. Weights and thresholds live in a `RiskModelConfig` **row, not a constant**, so a district engineer can retune after a false-alarm streak and the change is versioned.

**A bounded crowd-uplift multiplier.** Corroboration, verified reports and reporter trust lift the score — capped at **1.25×** by configuration. Deliberate: three neighbours reporting the same fresh crack within an hour should outrank a stale rain gauge, and one viral WhatsApp forward must not be able to move a district into evacuation.

**Escalation, not notification.** Alerts fire only when a ward's level *transitions upward* and no equivalent active alert exists inside a 90-minute dedupe window. Everything else is a state update. This is the difference between an early-warning system and a noise machine.

**Delivery as a pluggable provider with an honest ledger.** `console` is the default and records dispatches as `simulated`; `twilio` and `msg91` adapters make real REST calls when credentials are present. Every message writes a row with channel, language, provider, provider reference, status and timestamp. "Sent" and "would have been sent" are never conflated, and the API refuses to imply reach it did not achieve.

**Trilingual by construction.** Every alert is rendered in English, Hindi and Garhwali (Devanagari) before send — hazard names, level names and the concrete instruction attached to each level. Adding Kumaoni is a dictionary edit. The admin console previews all three variants, because a mistranslated evacuation order is worse than no order.

**Confidence, stated.** Each score carries a `confidence` in [0.10, 0.98] expressing how much of it is measured versus inferred from terrain priors. A ward with a live gauge and a drawn boundary is not the same as one scored from a slope angle, and the UI must not pretend it is.

## 4. Architecture

```
                     Open-Meteo (optional, USE_LIVE_WEATHER=true)
                                        |
  ingest service --- deterministic monsoon simulator (default, tagged 'simulated')
        |
        v
  TelemetryReading  --+
  Ward (terrain)  ----+--> risk_engine.score_ward()  --10 weighted factors--> score 0-100
  HazardReport    ----+                      |
  (crowd uplift)                             v
                                   level (green..red) + probability_24h
                                             |
                                             +--> WardRisk  (append-only, full factor breakdown)
                                             |
                              transition? ---+
                                             v
                            alerts.run_sweep -> Alert (localized en/hi/gar)
                                             |
                                             v
                            notifier.Dispatcher -> Provider (console | twilio | msg91)
                                             |                 SMS + IVR
                                             v
                                        Notification ledger (simulated | sent | queued | failed)

  React 18 / TS / MapLibre console  <--REST + WebSocket (/ws?channel=public|ops)-->  FastAPI
```

**Background heartbeat.** A monitor loop refreshes telemetry and runs the escalation sweep every `INGEST_INTERVAL_SECONDS` (default 900), inside the FastAPI lifespan, so a single process is a complete deployment.

**Live fan-out.** A WebSocket hub publishes `risk:update`, `alert:new`, `report:new`, `report:corroborated`, `shelter:update` and `road:update`. `public` carries anonymised scores only; `ops` requires a staff token. A replay buffer resends recent events on reconnect, which is what keeps a laptop-asleep demo from showing a stale screen.

**Stack.** FastAPI + SQLAlchemy 2 async (SQLite by default, PostgreSQL via `DATABASE_URL`) + Pydantic v2, bcrypt + PyJWT, httpx. React 18 + TypeScript + Vite + Tailwind + MapLibre GL + Recharts + react-i18next. Async ORM relationships use `lazy="selectin"` with no back-references, which keeps the whole app free of `MissingGreenlet` failures.

**Security posture.** Role gates (`citizen`, `field_responder`, `district_admin`, `system_admin`); self-registration can only ever mint a citizen; district admins are scoped to their own district; phone numbers are masked in the notification list view; identical error for unknown account and wrong password; SHA-256 pre-hash before bcrypt; request-timing and baseline security headers; production errors return a correlation id rather than internals.

## 5. How it works — a walkthrough

**Citizen.** Open the map: your ward is coloured by level, with the score, a 24-hour probability, and the dominant contributing factors in plain language. Tap **Report a hazard** — location, hazard type, severity, optional photo, works anonymously, because a tourist on the Mussoorie road with no account should still be able to report a crack. Tap **"I can see it too"** to corroborate a neighbour's report. See **nearest shelter with real free places** and capacity, and which lifeline roads are open. Read the **model** page: every weight, every threshold, and the disclaimer.

**Field responder.** Triage queue of open reports ordered by confidence; confirm or dismiss with a note (this is what moves reporter trust — confirmation +0.06, dismissal −0.10); dispatch a team to a report; update shelter occupancy and road status. Every write is actor-attributed in the audit log, because "who marked this road open?" is a question that gets asked.

**District admin.** Watch-room grid sorted by score with exposed-population roll-up. Author a warning, **preview it in all three languages**, then broadcast to one ward or a whole district. Retune weights and thresholds and save a new versioned `RiskModelConfig`. Run the **what-if drill runner**: inject a hyetograph for a ward and watch it escalate live, tagged `source='scenario'` so a drill can never be mistaken for an observation. Read the **delivery ledger**: sent vs simulated vs queued vs failed, by channel and by language.

## 6. Seed footprint

Real places, real coordinates, eight districts, forty wards: Dehradun, Pauri Garhwal, Tehri, Uttarkashi, Chamoli, Rudraprayag, Almora, Nainital — 210,200 modelled residents, 126,660 reachable phone numbers, 56,812 households, 51 rain/stage gauges, 18 shelters, 18 road segments, 12 deployable resource units, 11 open hazard reports, 7 demo accounts across all four roles.

Terrain values are **realistic engineering approximations for each location, not surveyed data**, and `backend/app/seed.py` carries that disclaimer as a constant in the repository. Section 9 covers this properly.

## 7. How to run it

**Backend** (Python 3.11+, zero configuration required):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload                        # http://localhost:8000/docs
```

On first boot it creates a SQLite database, seeds the eight districts and forty wards, generates a deterministic monsoon, runs the first escalation sweep and starts the monitor loop. No API keys, no network, no spend.

**Frontend:**

```bash
cd frontend
npm install
npm run dev                                          # http://localhost:5173
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so the demo needs no CORS configuration.

**Verification:**

```bash
cd backend && python scripts/smoke_test.py           # end-to-end checks against a running API
```

The script signs in at every role, reads the map, files and corroborates and confirms a report, escalates a ward with the scenario runner, previews all three languages, broadcasts an alert, and asserts that the delivery ledger recorded it as `simulated` rather than pretending it was sent. It also asserts negative cases: anonymous users cannot reopen a road, responders cannot trigger a sweep, and self-registration cannot mint an administrator.

**Demo accounts** (password `Aapaat@2026`): `collector.demo@aapaatsathi.in` (district admin), `field.demo@aapaatsathi.in` (responder), `citizen.demo@aapaatsathi.in`, `admin.demo@aapaatsathi.in` (system admin).

**Optional configuration** (all `.env`): `DATABASE_URL` for Postgres, `USE_LIVE_WEATHER=true` for Open-Meteo, `SMS_PROVIDER=twilio|msg91` with credentials for real dispatch, `CROWD_UPLIFT_CAP`, `DEDUPE_WINDOW_SECONDS`, `RESET_DATABASE=true`.

## 8. Open source

MIT licensed. [repo URL]. The repository is public from day one and the commit history covers the build phase, since the challenge asks teams to build in public. Contributions, issues and forks are welcome; the sections most useful to a state disaster cell are the risk engine and the provider abstraction, and both are deliberately small and commented. See `AI_AND_THIRD_PARTY_DISCLOSURE.md` for every third-party component and dataset used.

## 9. Limitations, stated plainly

1. **Not deployed, not field-validated.** No ward has ever been warned by this system and no resident has used it. Everything here is a working prototype against seeded data.
2. **The model is a susceptibility prior, not a trained predictor.** Weights are hand-set from published Himalayan landslide heuristics and local terrain priors. They are **not fitted to a labelled dataset**, because no ward-level, time-aligned Uttarakhand landslide event ledger exists to fit against. Claiming an accuracy figure would be fabrication.
3. **Terrain and population figures are approximations.** Slope, lithology, thrust distance, NDVI and population are plausible values for each named location, assembled so that exposure numbers are *computed* rather than asserted. They require GSI, Survey of India, Census and State DGRRM layers before any operational use.
4. **Default telemetry is a simulator.** Deterministic, reproducible, tagged `source='simulated'` in the database. The Open-Meteo adapter is real but has not been run at monsoon scale.
5. **Default delivery is simulated.** The console provider writes `simulated` rows and sends nothing. Twilio SMS is a real REST implementation; **Twilio IVR speaks only English in the current wiring** (`<Say language='en-IN'>`) — Hindi and Garhwali voice requires a language voice or a pre-recorded template. **MSG91 IVR is deliberately unimplemented** and returns a failure with a reason rather than pretending to succeed. No live dispatch to real residents has been performed.
6. **Reach numbers are modelled, not measured.** Beyond registered subscribers, the recipient resolver represents the ward's remaining registered-phone population as clearly-labelled synthetic numbers, capped per ward, so that exposure planning has a denominator. The API never labels these as delivered.
7. **The in-process dedupe map resets on restart.** The durable guard is the database-side active-alert check; a restart inside a dedupe window can permit one duplicate.
8. **Single-process state.** The WebSocket hub and throttle counters are in-memory; horizontal scaling needs a shared pub/sub backend.
9. **No landslide-specific glacio-hydrological modelling.** GLOF and rock-ice avalanches of the Chamoli type are physically distinct and outside this model's stated scope.
10. **No offline/disconnected path yet.** SMS and IVR survive poor data coverage, but if the towers are down the system is down. Radio and a store-and-forward fallback are roadmap items.

## 10. What we built for this hackathon

The entire project — idea, data model, risk engine, alert pipeline, delivery layer, localisation, API and console — was created for CodeSprint 2026. Nothing here is a pre-existing product, and no pre-existing project was forked.

Repository scope at submission: approximately 6,000 lines of backend Python across 8 routers, 7 services, 16 models and a seeding module; a React/TypeScript console with MapLibre mapping, live WebSocket state and trilingual i18n; an end-to-end smoke-test script. Third-party components, datasets and AI assistance are itemised in `AI_AND_THIRD_PARTY_DISCLOSURE.md` per Rules 1, 4 and 5.

## 11. Roadmap (plan, not progress)

1. Replace seeded priors with public geospatial layers: SRTM/CartDEM 30 m slope, GSI National Geomorphoscape lithology, Sentinel-2 NDVI anomaly, Census 2011 ward population, State DGRRM event records.
2. Calibrate weights and thresholds against a back-tested event ledger; publish precision/recall per level. Until a labelled ledger exists, this is the only honest path to an accuracy number.
3. Integrate IMD nowcasts and CWC bulletins as an authoritative override input alongside Open-Meteo.
4. Add Kumaoni and Nepali; record human voice IVR scripts in all languages rather than TTS.
5. Pilot with one block administration: one district, one monsoon pre-season, with an MoU on data handling and a named nodal officer.
6. SMS-in reporting (report by text from a feature phone) and a radio/SDR fallback for network outages.
7. Multi-tenant deployment per district with Postgres and role-scoped tenancy.

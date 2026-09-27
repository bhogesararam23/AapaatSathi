# Team & Task Plan — Build Phase 15 October – 15 November 2026

**Team:** 2 people. **Window:** Thu 15 Oct → Sun 15 Nov (31 days). **Finals:** Sun 22 Nov, Dehradun (in person).
**Weekly cadence (Devpost weeks run Wed–Tue):** W1 15–21 Oct · W2 22–28 Oct · W3 29 Oct–4 Nov · W4 5–11 Nov · W5 12–15 Nov.

> **On the two names below.** "Ram" is assigned the backend, data and infrastructure track; "Friend" is assigned the interface, demo and field track. These are attached to strengths, not to identities — **swap the names freely**, but keep the *pairing* of tracks intact. Splitting the model and the UI between two people who are not tracking each other is how a two-person project ends up with a beautiful screen over an empty API. Agree a single contract (the OpenAPI schema) on day 1 and neither track moves without it.

---

## 1. Reality check: what already exists

The plan front-loads this so nobody re-builds it. Verified on a cold boot, 27–28 September 2026.

### Done and verified

| Capability | Evidence |
|---|---|
| Risk engine — 10 weighted factors, weights sum 1.0, per-factor breakdown persisted, uplift capped 1.25 | `backend/app/services/risk_engine.py`; `GET /api/v1/risk/model` |
| Escalation on level transition with dedupe | `backend/app/services/alerts.py`; verified RPR-KND yellow→orange auto-issued one alert, immediate repeat issued zero |
| Delivery: console + Twilio + MSG91 providers, SMS/IVR, ledger distinguishing `simulated` from `sent` | `backend/app/services/notifier.py`; `GET /api/v1/notifications/stats` |
| Trilingual copy: English, Hindi, Garhwali alerts, IVR scripts, level/hazard names, advice per level | `backend/app/services/i18n.py` |
| Telemetry: deterministic simulator by default + real Open-Meteo adapter with graceful fallback | `backend/app/services/ingest.py` |
| What-if scenario / drill runner | `POST /api/v1/risk/scenario`; verified DEH-MUS yellow ≈56 → red 82.72 |
| Crowd reporting: anonymous filing, 1.2 km corroboration merge, explainable confidence, staff verdicts moving reporter trust | `backend/app/api/routes/reports.py` |
| Response assets: shelters with live free places, road status, resource units | `backend/app/api/routes/assets.py` |
| Auth + roles + audit trail | `core/security.py`, `core/deps.py`, `analytics/audit` |
| Seed footprint: 8 districts, 40 real wards, 210,200 residents, 51 gauges, 18 shelters, 18 roads, 12 resources | `backend/app/seed.py` |
| Live API: 54 operations, WebSocket fan-out on public/ops channels | `app.openapi()`, `/api/v1/ws` |
| End-to-end verification | `backend/scripts/smoke_test.py` → **61/61** on a fresh database, zero configuration |
| React/TS/Vite/Tailwind/MapLibre console: 9 routes, three surfaces, trilingual UI state, WebSocket live updates | `frontend/src/` (~4,400 lines of pages and components) |
| Submission copy for the whole hackathon | the six documents in `submission/` |

### Real gaps — this is the actual work of the month

1. **No public GitHub repository, no `LICENSE` file, no git history.** Open-source is a *required* step of this challenge and a named award. Currently non-compliant.
2. **Not deployed anywhere.** No URL a judge can open. Submission quality and 1st-place odds both hinge on this.
3. **Seeded terrain and population are approximations.** Slope, lithology, thrust distance, NDVI and ward polygons must come from public geospatial layers. This is the difference between a demo and a credible pilot.
4. **No unit tests** beyond the smoke script; no CI.
5. **UI/UX polish pass not yet done** — colour-blind-safe levels, Devanagari at 360 px, the factor waterfall as a signature visual, degraded-state rendering.
6. **No demo video.**
7. **No external feedback** — mentor or resident. Zero users have touched this.
8. **No travel booked** for a mandatory in-person final.
9. **Sponsor tasks unread.** Two Devpost to-dos exist whose contents could change our plan.

---

## 2. Week by week

Effort is in focused half-days per person, which is realistic around coursework. Each row has an acceptance test — if it cannot be checked, it is not a task.

### Week 0 (Mon 28 Sep – Wed 30 Sep, pre-build) — protect the entry, then rest

| # | Task | Owner | Acceptance |
|---|---|---|---|
| 0.1 | **Submit the idea before Sep 30, 17:00 IST.** Paste `submission/devpost-idea-submission.md`, proofread on a phone screen, confirm it appears under "My projects" | **Ram** | Screenshot of the submitted idea in the Devpost dashboard |
| 0.2 | Open both Devpost to-dos — **"Review Sponsor Task 1" and "Review Sponsor Task 2"** — read the full text, join the Elite Coders Discord, check Updates. If still ambiguous, email the hackathon manager one specific question | **Friend** | A written note: sponsor name, required technology, whether the award is conditional. If nothing is published, record "unresolved as of <date>" |
| 0.3 | Confirm both members are registered on the hackathon and that neither is affiliated with a company (eligibility, Rule: students only) | **Ram** | Both names appear under Participants |
| 0.4 | Set a weekly Monday reminder to re-check Updates and Discord through 15 Nov | **Friend** | Reminder exists |

Do not pre-build the MVP before 15 October. Get the entry in, read the sponsor tasks, then stop.

### Week 1 (15–21 Oct) — open-source compliance and a deployed URL

This week is about the two blocking gaps, not about new features.

| # | Task | Owner | Effort | Acceptance |
|---|---|---|---|---|
| 1.1 | `git init`, `.gitignore` (venv, `node_modules`, `data/*.db`, `data/uploads`, `.env`), add MIT `LICENSE` at root, push a **public** GitHub repo, start committing daily with real messages | **Ram** | 0.5 | Repo is public, loads without login, licence visible on the repo landing page |
| 1.2 | README: one-paragraph what, cold-boot commands, three screenshots, demo credentials, the honest-limits box, doc links, badge for the smoke test | **Friend** | 1 | A stranger following only the README reaches a working map in under 10 minutes. Test it on a second machine |
| 1.3 | Deploy the API publicly (Render / Railway / Fly.io free tier; SQLite volume or managed Postgres via `DATABASE_URL`). HTTPS, seeded on boot | **Ram** | 1 | `GET <url>/api/v1/health` returns `status: ok`, `seed_present: true` |
| 1.4 | Deploy the frontend (Vercel / Netlify / Cloudflare Pages), point `VITE_API_BASE` at the API, fix CORS to the real origins instead of `*` | **Friend** | 0.5 | The deployed map shows 40 live wards on a phone |
| 1.5 | GitHub Actions: install, run pytest + `smoke_test.py` against the deployed instance on every push | **Ram** | 0.5 | Green badge in the README |
| 1.6 | Move `submission/AI_AND_THIRD_PARTY_DISCLOSURE.md` into the repo and add `ASSISTED_WORKLOG.md` (per-module record of machine-generated code) and `CONTRIBUTING.md` + 4 good-first-issues | **Friend** | 0.5 | All four files linked from the README |
| 1.7 | **Sponsor technology decision** based on 0.2: adopt it through the existing seam, or record a written reason for not targeting that award | **Ram** | ≤1 | Either one merged adapter, or a paragraph in the submission notes |

**Week gate:** a judge can open a URL on a phone and see Ranikhot red, with no terminal involved. If this is not true by Sun 21 Oct, Week 2's discretionary work is cancelled and Week 1 continues.

### Week 2 (22–28 Oct) — real data in, tests underneath

| # | Task | Owner | Effort | Acceptance |
|---|---|---|---|---|
| 2.1 | Derive real **slope and elevation** per ward from SRTM/CartDEM 30 m (QGIS or a Python zonal-stat script); script it, commit the script, keep provenance in the file header | **Ram** | 2 | `slope_deg` and `elevation_m` recomputed from a DEM, not hand-entered |
| 2.2 | Replace **lithology** with GSI classes and **thrust proximity** with measured distance to MBT/MCT traces; document the source and the classification mapping in `docs/DATA_SOURCES.md` | **Ram** | 2 | Every ward's `lithology`/`fault_distance_km` traces to a named public layer or is explicitly marked still-approximate |
| 2.3 | Compute real **NDVI deficit** per ward from Sentinel-2; keep the 0.75 baseline as a published constant | **Ram** | 1 | `ndvi` no longer hand-typed |
| 2.4 | Ward boundaries and population: Survey of India / official ward or revenue outlines, Census counts. **If public ward-level geometry is unobtainable in a week — likely — document exactly what was obtained, what was substituted, and why.** Do not silently keep synthetic hexoids and imply otherwise | **Friend** | 2 | Data-provenance table published per ward; the disclosure document updated to match reality |
| 2.5 | Wire IMD nowcast / CWC bulletin endpoints if accessible; otherwise keep Open-Meteo and record the attempt | **Ram** | 1 | `USE_LIVE_WEATHER=true` produces real observations for all 40 wards, or a documented blocker |
| 2.6 | pytest units: `interp` curves, weight sum, level thresholds, `crowd_uplift` ceiling and monotonicity, `_confidence`, `ScenarioIn` validators, report-merge radius | **Ram** | 1.5 | `pytest` green; engine behaviour locked before any refactor |
| 2.7 | UI/UX polish pass part 1: hero watch-room screen, colour-blind-safe levels (glyph + colour, not hue alone), factor waterfall as the signature visual | **Friend** | 2 | Contrast-checked; a red/green colour-blind simulation still distinguishes every level |
| 2.8 | UI/UX polish pass part 2: Hindi and Garhwali rendering at 360 px with the longest real alert; degraded/empty states rendering `confidence`; three-tap report flow on a phone | **Friend** | 1.5 | Longest Garhwali SMS fits without clipping; a no-gauge ward visibly reads as uncertain |
| 2.9 | Ask for mentor feedback (CodeSprint says shortlisted teams get mentorship — take it; failing that, message one disaster-management or civil-engineering student/professional) and send the disclosure document to them on purpose | **Friend** | 0.5 | Written feedback log, plus at least one change made because of it |

**Week gate:** every terrain number either comes from a named public layer or is publicly labelled approximate. No unmarked approximations.

### Week 3 (29 Oct – 4 Nov) — the thing no other team will have: real people

| # | Task | Owner | Effort | Acceptance |
|---|---|---|---|---|
| 3.1 | **Test with real residents.** Target 6–10 people — family or contacts in Garhwal/Kumaon, ideally one hill ward and one town ward. Task: open the deployed map and find their own ward; read a Garhwali and a Hindi alert aloud; file one hazard report. Then two questions: *"would you act on this"* and *"what is missing"* | **Friend** | 2 | Written findings: what they could not do, what they distrusted, verbatim wording they suggested. **Expected outcome: real problems found. That is the deliverable** |
| 3.2 | Field-worker walkthrough: one person who has actually done relief or ward-secretariat work reviews the responder triage flow and the alert wording | **Ram** | 1 | Three concrete wording or flow changes merged |
| 3.3 | Fix the top 5 usability findings from 3.1/3.2 | **Both** | 1.5 | Re-test with two of the original participants; the blocker is gone |
| 3.4 | One **SMS-in** reporting spike — inbound text from a feature phone creating a `HazardReport`. Time-boxed to one day. **Explicitly allowed to fail**: ship it, or record the finding | **Ram** | 1 | Working inbound webhook demo, or a written post-mortem |
| 3.5 | Record the 2-minute demo video: sound-off-friendly captions, trilingual messages visible, live map, factor waterfall, the escalation and the ledger. Scripted from `pitch-deck-outline.md` §3 beats | **Friend** | 1.5 | Uploaded and embedded in the submission; watchable with no audio and no context |
| 3.6 | Publish the model methodology page: factor sources, curves, thresholds, what would change a weight, and the calibration protocol | **Ram** | 1 | `/model` page and `docs/MODEL.md` state the same thing |
| 3.7 | Ask one district disaster cell, NDRF or SDMA contact for feedback on realism. **A request for a review, not a claim of partnership** | **Both** | 0.5 | An email thread. A reply is a bonus; a "no" is still evidence of the pathway |

**Week gate:** at least six real humans have used the deployed system and we have written down what broke. Report findings honestly in the submission — including negative ones.

**Integrity rule for the whole project, agreed now:** we never claim a user, a deployment, a partnership or an accuracy figure that does not exist. "Piloted with N residents" means they opened it and we watched. Anything softer is a number we would have to retract on stage in Dehradun in front of people who live there.

### Week 4 (5–11 Nov) — submission quality and the pitch

| # | Task | Owner | Effort | Acceptance |
|---|---|---|---|---|
| 4.1 | Freeze features. Bug fixes and copy only | **Both** | — | Tag `v1.0-submission`; the tag matches what is deployed |
| 4.2 | Update `devpost-project-submission.md` against reality: fill every bracketed slot, delete anything that stopped being true, re-check every number against a live instance | **Ram** | 1 | A second person reads it and finds no claim contradicted by the code |
| 4.3 | Update `AI_AND_THIRD_PARTY_DISCLOSURE.md`: every library added since September, exact versions, the resident-testing data-handling note, and the real data-provenance outcome from 2.4 | **Friend** | 1 | Section 5's table matches the repository as it now stands |
| 4.4 | Demo **credentials and accounts** verified on the deployed URL; reset the deployed database so judges start clean; confirm zero real personal data | **Ram** | 0.5 | Fresh judge boot shows 40 seeded wards |
| 4.5 | Rehearse the 7-minute pitch, then the demo script three times **against a fresh database**, including the fallbacks table | **Both** | 1.5 | Timed at ≤7:00 with no slide left on screen over 60 s; both can run the demo alone |
| 4.6 | Answer all 14 questions in `pitch-deck-outline.md` §4 out loud, cold, to each other | **Both** | 0.5 | Neither stalls on "what is your accuracy" or "how many users" |
| 4.7 | **Book travel and stay for Dehradun, 21–22 Nov** (Rule 7 requires finalists to attend offline) | **Friend** | 0.5 | Tickets confirmed. Do not leave this to submission week |
| 4.8 | Open-source readiness sweep: licence headers, no secrets, `git log` legible, issues open, a `CHANGELOG`, good-first-issues labelled | **Ram** | 0.5 | Best-Open-Source checklist passes |

### Week 5 (12–15 Nov) — submit, then sharpen

| # | Task | Owner | Acceptance |
|---|---|---|---|
| 5.1 | Complete every Devpost form field: URL, repo, video, deployed app, source, team, licence, the 3rd-party and AI-disclosure boxes | **Ram** | Submission status "submitted", well before 15 Nov close |
| 5.2 | Run the whole pre-submission checklist in §4 below, on the deployed URL, on a phone | **Friend** | Every box ticked and signed |
| 5.3 | Prepare for shortlist notification; keep the deployed instance warm and monitored | **Ram** | Uptime check on the day of judging |
| 5.4 | Final pitch rehearsal in the room layout we expect (projector, own laptop, one presenter at the keyboard) | **Both** | One clean run, one deliberate-failure run |

**Sun 15 Nov — submission deadline. Sun 22 Nov — Dehradun.**

---

## 3. Track ownership at a glance

| Track | Owner | Scope |
|---|---|---|
| Model, data, infrastructure | **Ram** | Risk engine, geospatial ingestion, providers, database, deployment, CI, API contract, accuracy-honesty guardrail |
| Interface, demo, field | **Friend** | Console and citizen UI, UI/UX polish, demo video, resident testing, disclosure and submission copy, travel logistics |
| Shared decisions | **Both** | What we claim publicly; sponsor adoption; feature freeze; the pitch narrative |

Two rules that keep a 2-person project coherent: **the API contract is frozen for a week at a time**, so the UI is never chasing a moving backend; and **neither person ships a public claim the other has not read.**

---

## 4. Pre-submission checklist — mapped to the actual Devpost rules

Sign each line with a name and a date. Anything unverified is left blank rather than ticked.

### Rule compliance

| # | Rule | Requirement | Check | Status |
|---|---|---|---|---|
| R1 | Original Work (1) | Project created specifically for CodeSprint | Repo history and README state the origin; the fact that a proof-of-concept engine was written **before** shortlisting (to substantiate feasibility in the idea round) is disclosed explicitly, not hidden | ☐ |
| R1b | Original Work (1) | **Clearly disclose pre-existing code, components, libraries, APIs, datasets** | `AI_AND_THIRD_PARTY_DISCLOSURE.md` in the repo and linked from the submission; nothing used that is not listed | ☐ |
| R2 | Open Source | **Public GitHub repository** | Open the repo URL in a private browser window; it loads without login | ☐ |
| R2b | Open Source | **Appropriate open-source licence** | `LICENSE` file present at root, OSI licence (MIT), shown in GitHub's licence badge | ☐ |
| R3 | Team Size | 2–5 members; **all members listed on the Devpost submission** | Both names in the submission team list and both registered on the hackathon | ☐ |
| R3b | Eligibility | Students only; no company or professional-organisation participation; above age of majority in country of residence | Confirmed for both members | ☐ |
| R4 | AI Tools | AI assistance permitted; participants responsible for the submission | Tools and roles named in §2 of the disclosure; `ASSISTED_WORKLOG.md` file-level record; a human on this team can explain every shipped line | ☐ |
| R5 | Third-Party Tools & APIs | Used subject to their licences and terms | §3 of the disclosure lists each with its licence; MapLibre demo tiles replaced or flagged; Open-Meteo non-commercial terms checked; no keys in the repo | ☐ |
| R6 | Submission Deadline | Completed by **15 November 2026** | Full submission uploaded; not a placeholder update on the last hour | ☐ |
| R7 | Final Pitch | Available in person in Dehradun on **22 November 2026** | Travel and stay booked for both members, with a contingency if one cannot attend | ☐ |
| R8 | Code of Conduct | Respectful, inclusive, professional | Pitch language reviewed: no disparagement of other entries, of government bodies, or of IMD/SDMA — we position as complementary, never as "they failed" | ☐ |
| R9 | Intellectual Property | We retain IP, subject to third-party licences | No CLA or assignment signed with anyone; third-party licences satisfied | ☐ |
| R10 | Disqualification | No plagiarism, no misrepresented contributions | Every claim traceable to code or marked as plan; contribution split stated | ☐ |

### Submission package quality

| Item | Check | Status |
|---|---|---|
| Deployed URL | Loads over HTTPS on a phone in ≤10 s; 40 wards visible; no console errors | ☐ |
| Demo video | ≤3 min, watchable with sound off, shows the map, the escalation, the three languages and the ledger | ☐ |
| Source link | Points to the public repo, not a fork of someone else's starter | ☐ |
| Licence field on the form | Filled in as MIT, matching the `LICENSE` file | ☐ |
| Working demo credentials | `collector/field/citizen/admin.demo@aapaatsathi.in` with `Aapaat@2026` all sign in on the deployed URL | ☐ |
| API docs | `<url>/docs` reachable and describes 54 operations | ☐ |
| Model transparency | `<url>/api/v1/risk/model` returns `weights_sum = 1.0` and the disclaimer | ☐ |
| Verification | `smoke_test.py` passes against the deployed instance; the command is in the README | ☐ |
| Limitations section | Present, specific, and free of hedged bravado | ☐ |
| No fabricated numbers | Grep the submission for users, accuracy percentages, deployments, partnerships, MOUs — every surviving claim is real | ☐ |
| Sponsor award | Either genuinely used with a code location named, or not claimed | ☐ |
| Social-welfare framing | Opens with one person's decision, not a statistic | ☐ |
| Beginner-team line | Included, if true | ☐ |
| Consistency | Idea text, README, submission description and pitch script tell the identical story | ☐ |

---

## 5. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Sponsor tasks turn out to require an unfamiliar platform | Medium | Decide by 21 Oct, not 10 Nov. The provider and ingest seams exist precisely so this is a one-day job |
| Public ward-level geospatial data proves unobtainable in a week | **High** | Ship what is genuinely available (DEM slope is easy; official ward polygons are hard), publish a per-ward provenance table, and state the substitution openly. Honest partial data beats fictional complete data |
| Deployment free tier dies before judging | Medium | Keep a one-command local run as the guaranteed fallback; record the demo video early so a dead URL is never fatal |
| Real-SMS costs before we have any budget | Certain | Never enable a paid provider against seeded phone numbers. Console provider is the default for good reason |
| Coursework or exams collide with Week 3 | Medium | Week 3 is the softest week to slip; Weeks 1, 2 and 4 are the ones that decide the outcome |
| UI/UX polish consumes the data-replacement work | Medium | Sequence it: W1 deployment and repo, W2 data and polish in parallel tracks, W4 freeze. Do not let the prettiest track eat the most load-bearing one |
| One member becomes unavailable | Medium | The API contract plus the smoke test mean the other can drive the demo alone; `pitch-deck-outline.md` §3.4 exists so the stage never depends on one keyboard |
| We overclaim under pitch adrenaline | Low, catastrophic | Q&A rule: volunteer the limitation first. "Zero users" is a stronger answer on a Dehradun stage than a number we cannot source |

---

## 6. Success criteria on 15 November

Not a wish list — the checks we will actually grade ourselves on:

1. A stranger opens the deployed URL on a phone and sees their own district without instructions.
2. The public repo has an MIT licence, a README that works on a second machine, a green CI badge, and legible commits across all five weeks.
3. Every terrain and population number is either sourced to a named public layer or publicly labelled approximate.
4. At least six real people have used it and we can list what broke.
5. `smoke_test.py` passes against the deployed instance.
6. Every claim in the submission is traceable to code, and every non-claim is disclosed.
7. Both members are in Dehradun on 22 November, and one of them can run the whole demo alone.

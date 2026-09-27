# Awards Strategy — Elite Coders CodeSprint 2026

**Objective:** place 1st, and collect every special award that costs nothing once the substance already exists.
**Field:** 42 registered participants. Teams are 2–5, so realistically **~12–18 submitted projects** at Devpost close — several will be empty repos.
**Published judging criteria:** one line — *"Idea needs to be Impactful."* No weights published. Judge of record: Nishant Rana (Program Manager, Elite Coders) and others.

That single line is the whole strategy: **an unambiguous human-impact story beats an impressive technical story here.** Impact is our strongest axis, so we lead with it everywhere — idea text, README first screen, pitch slide 2, demo video first ten seconds.

---

## 1. Expected-value ranking

Assumptions, stated because they are guesses: roughly equal judging attention per award; our project is top-decile on domain substance and mid-decile on visual polish unless we spend deliberately; special awards are usually decided from the same submission package as the main prize.

| Rank | Target | Cash/Value | Our fit | Est. P(win) if we execute | Cost to raise it | Verdict |
|---|---|---|---|---|---|---|
| 1 | **Best Social Welfare Project** | Swag kit ×2 | Extreme — this is literally what the product is | **High (40–55%)** | Low. Already true; only needs signposting | **Do it. Cheapest award in the field.** |
| 2 | **Best Open Source Project** | Swag kit ×2 | Strong, but **currently unmet**: no public repo, no licence file | **High once fixed, ~0 until fixed** | Low–medium: repo hygiene, not new features | **Highest-leverage 4 hours in the whole month.** |
| 3 | **1st Place** | ₹15,000 | Top-contender if it reaches human judges; weaker against a sponsor-technology entry | **Medium (15–25%)** | High: demo video, public deploy, deployed URL, polish | **Primary. Everything below feeds it.** |
| 4 | **Best Innovation** | Swag kit ×2 | Good, on a specific defensible claim (bounded crowd uplift + auditable-per-score + honest ledger) | **Medium (20–30%)** | Low: naming the innovation clearly in copy | Do it after 1 and 2 |
| 5 | **Best UI/UX** | Swag kit ×2 | Contingent — the substance exists, the screen must be rehearsed | Low now (**5–15%**), **30–40%** with a focused polish pass | Medium: 2–3 days, no new features | Only after items 1–4 are done |
| 6 | **Best Beginner Team** | Swag kit ×2 | Free if either member is entering a first hackathon | **High** | Zero | Claim it in the submission text |
| 7 | **2nd / 3rd Place** | ₹10,000 / ₹5,000 | Falls out of doing 1–4 well | Medium | — | Do not target separately |
| 8 | **Best Use of Sponsor Technology** | Swag kit ×2 | **Un-targetable today** — see Section 5 | **~0 with current information** | Unknown until the tasks are published | One action: read the tasks |

Read the table's real message: **three of the top five cost almost nothing and are already true of our project.** We do not need to build more product to win awards; we need to make the existing substance legible in five hours of documentation and repo hygiene.

---

## 2. Best Social Welfare Project — evidence map

**What a judge looks for:** a named population, a mechanism that reduces harm, a plausible route to real use, and a team that understands who is actually affected rather than who is conveniently measurable.

| Evidence | Where it lives |
|---|---|
| The problem is specific, dated and local — Ranikhot Aug 2021 (~50 dead), Dharali and Silyari Oct 2021, Karnaprayag Feb 2021, Chhilbikhuna annually, Jakholi/Kirartoli Jul 2023 | `submission/devpost-idea-submission.md`; ward `notes` field seeded in `backend/app/seed.py` (`HISTORICAL_NOTE`); visible on the ward page |
| Beneficiaries are modelled, not asserted: 40 wards, 210,200 residents, 126,660 reachable phone numbers, 56,812 households, with per-ward children, elderly and disabled counts feeding the exposure figure | `EXPOSURE_FRACTION` and `population_at_risk` in `backend/app/services/risk_engine.py`; surfaced by `GET /api/v1/analytics/coverage` and `GET /api/v1/risk/overview` |
| It reaches the people a smartphone app cannot: SMS + automated voice call, English/Hindi/Garhwali, and voice only at orange/red | `backend/app/services/notifier.py`; `backend/app/services/i18n.py` |
| It will not spam the population it serves — escalation on transition, 90-minute dedupe | `backend/app/services/alerts.py` (`run_sweep`); demo beat 1's `created: 0` on repeat |
| Shelter capacity and road status so a warning has somewhere to go | `backend/app/api/routes/assets.py`; `GET /api/v1/shelters` with real free places and distance |
| It cannot lie about reach | `GET /api/v1/notifications/stats`, `simulated` vs `sent` |

**Free upgrades, do all four:**
1. Open the README, the demo video and the pitch with **one person's decision**, not a statistic: a Garhwali SMS arriving at 2 a.m. and the sentence that tells that household to move.
2. Show the Garhwali message rendered on a phone-shaped viewport in the demo video. Nobody else in the field will have a non-English screen.
3. State the cost of a warning per household alongside the cost of the event it prevented. Section 8 of the project submission already has the arithmetic.
4. Add one line to the submission: *"No resident has used this. That is the gap, and closing it is the roadmap."* Volunteering it is what separates a welfare project from a welfare aesthetic.

**Risk to manage:** the award goes to the team that seems likeliest to actually help somebody. Avoid sounding like a rescue fantasy — the credibility comes from the limitations section, not from the mission statement.

---

## 3. Best Open Source Project — the blocking gaps

**What a judge looks for:** a genuinely public repo, an OSI licence, a README a stranger can run in ten minutes, real commit history showing the build happened during the challenge, contribution docs, and code that survives being forked.

| Requirement | Status today | Action |
|---|---|---|
| Public GitHub repository | **Absent** — no git history at all | `git init`, commit now, push day one of the build phase and commit throughout. History is the evidence |
| Open-source licence | **Absent** — MIT is declared in the FastAPI metadata but no `LICENSE` file exists | Add MIT `LICENSE` at repo root. Cross-check every dependency licence in `submission/AI_AND_THIRD_PARTY_DISCLOSURE.md` §3 |
| README that gets a stranger running | Must be written | Structure: one-paragraph what, the cold-boot command block, three screenshots, demo credentials, the honest-limits box, doc links |
| Reproducible build from zero | **Verified working** — cold boot seeds 8 districts / 40 wards and runs the first sweep with no keys, no network, no config | Document the exact commands. This is already better than most entries |
| Verification a reviewer can run | `backend/scripts/smoke_test.py` → **61/61** on a cold boot | Put the pass count and the command in the README and the submission text |
| Tests in CI | Partial — smoke script, thin `backend/tests/` | Add pytest unit coverage for the risk engine (curves, weight sum, uplift cap, transition logic) and GitHub Actions running both on every push |
| `CONTRIBUTING.md`, issue templates, security note | Absent | Write them; also add a good-first-issue list. Reviewers click these |
| Docs beyond the README | Swagger at `/docs`, `GET /api/v1/risk/model` as a published methodology page | Link them explicitly; add a short `docs/ARCHITECTURE.md` |
| Disclosure of AI assistance and third-party parts | **Written** | `submission/AI_AND_THIRD_PARTY_DISCLOSURE.md` → move into the repo. Very few entries will have one |

**The one thing that wins this award:** build in public *during* 15 Oct–15 Nov with legible commits, and make the repository pleasant. It is not about star counts. Two of the requirements above are currently failing, and both are fixable in an afternoon — which is why this is the highest-leverage block of work in the month.

---

## 4. Best UI/UX — what will actually be judged

Judges score the screen they are shown for ninety seconds. Domain depth does not transfer. Our honest position: strong information architecture, untested visual polish.

**What already exists to build on** (`frontend/`, ~4,400 lines of pages and components):
- Live MapLibre ward map with per-level colour tokens and a WebSocket feed, no refresh required
- Nine routes: Home, Ward, Report, Shelters, Roads, Model, Sign In, Responder, Console — a real three-surface product, not a dashboard with tabs
- Trilingual interface via i18next (`en`/`hi`/`gar`), so the UI itself demonstrates the reach argument
- Touch targets at a 44 px minimum with a "glove- and sunlight-friendly" note, `:focus-visible` styling and `prefers-reduced-motion` support — field-usable accessibility, not decoration
- A public **model** page exposing every weight, threshold and disclaimer — transparency as a designed screen
- Error boundaries, loading skeletons, toast notifications, and an admin alert preview in all three languages before send

**The 2–3 day polish pass, in priority order:**
1. **One hero screen.** The watch-room map is the shot in the video and on stage. Nothing else appears in the first 30 seconds.
2. **Colour-blind safety.** Five levels differentiated only by hue will lose the UI/UX award on accessibility grounds. Add a level glyph or letter and a patterned border; keep red/orange/green for the majority.
3. **Hindi and Garhwali rendering.** Devanagari at current sizes may clip or wrap badly. Test the longest Garhwali alert on a 360 px phone. A broken localised screen is worse than an English-only one because it falsifies the headline claim.
4. **The factor waterfall as the signature visual.** Ten stacked contributions summing to a score is a distinctive, honest graphic nobody else will have. Put it on the ward page and on slide 7.
5. **Empty and degraded states.** A ward with no gauge and no reports must look uncertain, not safe — the `confidence` field already computes the number; render it.
6. **Mobile report flow.** Report-a-hazard is the citizen path; make it three taps to submit on a phone and record it that way in the video.
7. Delete or clearly badge anything that looks like debug scaffolding (`VITE_SHOW_DEV_TOOLS` panels) from the frames judges see.

**Do not** add charts, dark mode, animation, or a second map layer for the sake of it. Polish pass means subtraction.

---

## 5. Best Use of Sponsor Technology — blunt assessment

**We cannot target this award right now, and anyone claiming otherwise is guessing.** The page has a "Hackathon Sponsors" section, the Devpost to-dos list **"Review Sponsor Task 1"** and **"Review Sponsor Task 2"**, and there is a **Best Use of Sponsor Technology** swag award — but neither sponsor names nor task descriptions appear in the captured pages. Any work spent guessing a sponsor stack is a coin flip paid for with build time.

Concrete actions, in order, no later than **1 October 2026**:

1. Open both Devpost to-dos on the hackathon dashboard and read the full task text. They are individually assigned to our account, which means they are the authoritative statement of what sponsors want.
2. Join the Elite Coders **Discord** (the To-dos panel surfaces "Go Join Discord") and check `#announcements`. The Resources page states outright that *"All major CodeSprint announcements, mentorship information, deadlines, and updates will be shared through the official Elite Coders communication channels"* — so sponsor tasks are more likely to be clarified there than on the static page.
3. Check the **Updates** tab and the Rules/Overview pages again near the build-phase start, and set a reminder to re-check weekly through 15 November.
4. Reply to the "Questions? Email the hackathon manager" link with one short, specific question if the tasks are still ambiguous: what the sponsor requires, whether use is mandatory for the award, and whether a hosted free tier is expected.

**The fallback — and it is genuinely good news.** If the tasks turn out to be unusable, unknown, or platform-mismatched: stop and rely on the two axes where we already win (Social Welfare and Open Source), because a forced sponsor integration is a distraction from the ₹15,000 argument. In the meantime, keep the sponsor surface **cheap to satisfy**, because that is what makes an opportunistic integration a one-day job rather than a rewrite:

| Sponsor tech commonly requested | Our existing seam | Cost if we must comply |
|---|---|---|
| Cloud SMS / notifications API | `BaseProvider` in `notifier.py`; `build_provider()` selects by env var. Twilio and MSG91 adapters already exist | Add one adapter class. Under an hour |
| Weather / geospatial / mapping API | `ingest.fetch_open_meteo()` plus `USE_LIVE_WEATHER`; MapLibre with a swappable style object | Add one fetch function. Under a day |
| Cloud hosting / database | SQLite default, Postgres via `DATABASE_URL`; single-process ASGI app | Deploy. Under a day |
| AI/LLM API | None used at runtime, by design | **Do not bolt one on to win an award.** If a sponsor task explicitly requires it, the right integration is summarising a factor breakdown into plain-language advice text in each language — genuinely useful, and it keeps the risk model untouched |
| Auth/provider | JWT + bcrypt already isolated in `core/security.py` | Contained |

State whatever we do plainly in the submission: *"we adopted X for Y reason, at Z location in the code."* A judge can verify that in two clicks. An unstated token gesture verifies as nothing.

---

## 6. Best Innovation — name it, or it does not count

Innovation gets awarded to the team that can state one thing nobody else did, in a sentence. Ours, ranked by defensibility:

1. **Bounded crowd uplift.** Ground truth is treated as a *multiplier with a hard ceiling*, not as an additive vote. It solves the actual problem in this domain — crowdsourcing a warning system invites weaponisation — and the fix is 20 lines of legible arithmetic with a configurable cap. Nobody else in a beginner-friendly field will have designed against their own input channel.
2. **Auditability as a first-class stored artefact.** Every score persists its full per-factor contribution breakdown, and the model itself is a versioned database row rather than constants — so a warning can be reconstructed and defended months later, and thresholds retuned without a redeploy.
3. **An anti-overclaiming delivery ledger.** `simulated` versus `sent` is a real distinction most projects elide, including in their own submissions. This is an unusual kind of innovation — epistemic rather than technical — and the fact that our default provider can never accidentally message twelve thousand phone numbers is a design decision worth a slide.
4. **Warning granularity decoupled from administrative geography.** District-level alerts for a ward-sized hazard is the specific institutional failure being fixed.

Present these four as the innovation answer and never as a checklist. Lead with number 1; it is the one that makes a judge repeat it to another judge.

**Best Beginner Team:** if either member is entering a first hackathon, say so in one line in the submission and the pitch ("two students, first build challenge, month-long, and we documented what we did not do"). This award is frequently under-submitted and the cost is one sentence. Devpost also lists Achievements for "First online hackathon" and "Generalist", so a complete submission helps here independently.

---

## 7. The 1st-place argument, and where it is contested

Against a field of ~12–18 student projects, our case is: **real domain problem, verifiable working system, publishable honesty, and a pitch that lands in the room.** The likely competition for 1st is (a) a polished consumer app that demos beautifully, and (b) whichever project best satisfies a sponsor task if that becomes a stated short-cut to the main prize.

To beat (a): a deployed URL that loads on a judge's phone, a 2-minute demo video cut for sound-off viewing, a README that runs in ten minutes, and a single memorable number — Ranikhot, 77.86, red, 5,530 people exposed on a cold boot with no configuration.

To beat (b): Section 5's actions, executed before the build phase starts, not after it.

**The submission package a judge actually reads, in the order they read it:**
1. Project title and the first sentence of the description → impact in one line.
2. Demo video → does it work, does it look considered.
3. Deployed URL → does it load on a phone.
4. Repository → licence, README, commits.
5. Written description → architecture, limitations.
6. Source/3rd-party/AI-disclosure fields → we pre-empt this with `AI_AND_THIRD_PARTY_DISCLOSURE.md`.

Note what is *not* in that list: model sophistication. Optimise accordingly.

---

## 8. Sequenced plan (feeds `TEAM-AND-TASKS.md`)

| When | Action | Award it moves |
|---|---|---|
| **Before 30 Sep, 17:00 IST** | Submit the idea. Problem-first, impact-first, ≤650 words, no overclaim: `devpost-idea-submission.md` | Entry ticket to everything |
| Week 0 (before 15 Oct) | Read Sponsor Tasks 1 and 2 on the dashboard; join Discord; email the hackathon manager if ambiguous | Sponsor, and de-risks the main prize |
| Week 1 (15–21 Oct) | Public GitHub repo, MIT `LICENSE`, README, `git init` and start committing daily, CI | **Open Source** (currently 0% → high) |
| Week 1–2 | UI/UX polish pass: hero screen, colour-blind levels, Devanagari on a 360 px phone, factor waterfall | **UI/UX** |
| Week 2–3 | Public deployment + HTTPS + Postgres; smoke test running against the deployed URL | 1st place, Open Source |
| Week 3 | Real geospatial data replacing seeded priors; publish the change | 1st place, Innovation, credibility |
| Week 3 | 2-minute demo video, sound-off, three languages visible | UI/UX, 1st place |
| Week 4 (before 15 Nov) | `CONTRIBUTING.md`, good-first-issues, pytest units, disclosure docs into the repo, submission fields filled, all members listed | Open Source, Social Welfare, rule compliance |
| Week 4 | One-line "first hackathon" claim if true; four-sentence innovation statement in the description | Beginner Team, Innovation |
| Nov 16–21 | Book travel to Dehradun, rehearse the pitch five times including the demo fallbacks, print the disclosure doc to hand over | 1st place |

**Do not spend build time on:** microservice decomposition, Kubernetes, a mobile app, an AI/LLM feature added for the sake of it, multi-region deployment, auth hardening beyond what a demo needs, or more than eight wards of extra seed data. None of these move a single row in Section 1.

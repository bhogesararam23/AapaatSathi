# Stage Pitch — Elite Coders CodeSprint 2026 Final Pitch, Dehradun, 22 November 2026

**Format:** ~7 minutes presenting + Q&A with judges in the room.
**Presenters:** 2. Split below. Rehearse at least three full dry runs against a **fresh database**, and one with the primary network path disabled.
**Audience note:** the room is in Dehradun, Uttarakhand. Almost everyone in it has a landslide story, has driven NH-73 in August, or knows somebody who was at Ranikhot. Do not explain the mountains to them — name the places and let the room fill in the memory. The local disaster record is the strongest asset we have; use it deliberately, without melodrama.

---

## 1. Run of show

| # | Time | Segment | Owner | Slide |
|---|---|---|---|---|
| 1 | 0:00–0:20 | Cold open: one sentence, no slide title | Friend | S1 |
| 2 | 0:20–1:20 | The problem: wrong scale, wrong channel | Friend | S2–S3 |
| 3 | 1:20–2:00 | The insight, in one line | Friend | S4 |
| 4 | 2:00–4:30 | **Live demo** (three beats) | Ram | S5 (browser only) |
| 5 | 4:30–5:15 | How it works: architecture + transparency | Ram | S6–S7 |
| 6 | 5:15–6:00 | Impact, honesty about limits, path to a district | Ram | S8–S9 |
| 7 | 6:00–6:40 | Team and the ask | Friend | S10–S11 |
| 8 | 6:40–7:00 | Close on the first line | Friend | S1 (return) |

Standing rule: whoever is not speaking drives the terminal. Nothing waits on a page load.

---

## 2. Slide by slide

### S1 — Title
**AapaatSathi (आपतसाथी) — a companion in disaster**
Ward-level landslide and flash-flood early warning for Uttarakhand.
Repo URL · deployed URL · two names.

Cold open, delivered to the room, not to the screen:

> "In August 2021, about fifty people died at Ranikhot. They were standing under the slope that came down. The district was already under a red alert. That alert was true, and it saved nobody — because you cannot evacuate a district."

### S2 — The problem: wrong scale
Map of one district with a single red wash over it, next to a 300-metre ward.

- Districts in this state run to thousands of square kilometres. A hill ward is a few hundred metres across.
- "Red alert: Pauri Garhwal" is simultaneously correct and unusable for the forty families below one escarpment.
- Same district: one ward is a granite ridge, another is a Siwalik toe under NH-73 with a drain running through it.

### S3 — The problem: wrong channel
Photograph-free, one line of type plus three numbers.

- The households most exposed to slope failure — lower slopes, riverbanks, old settlements — are the least likely to hold a charged smartphone with data.
- An app-based warning reliably reaches the people who were already safest.
- So: **SMS and an automated voice call. English, Hindi, Garhwali.** Not a notification. A phone that rings in a dark house.

### S4 — The insight
One sentence, centre screen, nothing else:

> **Warn the hillside, not the district — and reach the phone people actually have.**

Say the corollary out loud: *"Everything else in the next seven minutes is engineering around those two lines."*

### S5 — Live demo
Single slide: the deployed URL and the AapaatSathi wordmark. The room watches the browser from here. Script in Section 3.

### S6 — How it works
The architecture diagram, projected at a size people can read:

`telemetry (Open-Meteo or simulator) + terrain priors + crowd reports → 10-factor susceptibility score → level transition → SMS + IVR fan-out → delivery ledger`

Three callouts only:
- Fifteen-minute sweep, forty wards, one process.
- Alerts fire on **level transition**, not on every computation — the dedupe window is part of the model.
- Every dispatch writes a ledger row. `simulated` and `sent` are never conflated.

### S7 — Why you should believe the number
Screen the `GET /api/v1/risk/model` output and a live factor waterfall.

- Ten factors, weights summing to exactly 1.0, each piecewise-normalised, each with a written rationale.
- **Every historical score persists its own breakdown** — you can reopen any ward at any minute and see the contribution of each term.
- Weights and thresholds are a **database row**, not a constant. A district engineer retunes after a false-alarm streak, and the change is versioned.
- Then the honest part, said clearly: *"This is a susceptibility prior, not a trained predictor. There is no ward-level, time-aligned Uttarakhand event ledger to train on, so an accuracy number from us would be a fabricated number. We would rather show you a prior we can defend line by line."*
- Crowd uplift capped at 1.25×: *"Three neighbours confirming a fresh crack beat a stale rain gauge. One WhatsApp forward cannot evacuate a town."*

### S8 — Impact and what is real today
Two columns. **Built** versus **not claimed.**

| Built today | Not claimed |
|---|---|
| 8 districts, 40 real wards, 210,200 modelled residents | Any real-world deployment |
| 54 API operations, 3 surfaces, live WebSocket map | Any resident has ever been warned |
| End-to-end verification: 61/61 checks on a cold boot | A trained model or an accuracy figure |
| SMS + IVR in 3 languages with a delivery ledger | Government adoption or endorsement |

Then the arithmetic of the ask: at roughly ₹1–2 per SMS, warning the 126,660 reachable phone numbers in our modelled pilot footprint costs about ₹1.5–2.5 lakh per alert round. One family moving uphill at 2 a.m. is worth more than that. *(Label these as indicative telecom tariffs, not a quotation.)*

### S9 — Path to a district
Plan, drawn as a plan, not as progress:

1. Replace seeded priors with public geospatial layers — SRTM/CartDEM 30 m slope, GSI National Geomorphoscape lithology, Sentinel-2 NDVI, Census ward population, State DGRRM event records.
2. Calibrate against a back-tested event ledger; publish precision, recall and false-alarm rate per level.
3. Pilot with **one block administration**, one pre-monsoon season, named nodal officer, recorded human-voice Hindi and Garhwali IVR scripts.
4. Report-by-SMS-in from a feature phone, and a radio fallback for when the towers are down.

Audience cue for a Dehradun room: *"GSI and the State DGRRM are in this city. The data we need is 10 kilometres from this stage. That is the entire reason we built this here."*

### S10 — Team
Two names, two lines each: who writes the backend and who owns the interface and the field story, plus one honest line — *"Two students, one month, and we documented what we did not do."* Point at `AI_AND_THIRD_PARTY_DISCLOSURE.md` by name. Judges notice a team that volunteers its limitations before being asked.

### S11 — The ask
Three specific requests:
1. An introduction to one block development officer or district disaster cell in Uttarakhand for a pre-monsoon pilot.
2. Review of the risk weights by somebody with geotechnical or hazard credentials — we will publish their critique.
3. Sponsor or platform support for SMS and voice credits to run a real pilot (this is also our answer to Best Use of Sponsor Technology — see `AWARDS-STRATEGY.md`).

Close on the first line, inverted:

> "Fifty people died at Ranikhot while their district was under a red alert. Give a ward its own warning, and put it on the phone its residents actually own. That is all AapaatSathi is."

---

## 3. Live demo script (~2 min 30 s)

### 3.0 Non-negotiable setup

```bash
# Fresh database so no stale alert suppresses the live fan-out.
cd backend
rm -f data/aapaatsathi.db           # or set RESET_DATABASE=true
export SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
uvicorn app.main:app --port 8000    # watch the boot log: seed + first sweep + [SIMULATED SMS] lines
cd ../frontend && npm run dev       # http://localhost:5173
```

Two windows side by side: **browser** (map + console) and **terminal** (`curl -s | jq`). Log in once as `admin.demo@aapaatsathi.in` (password `Aapaat@2026`) and export the token:

```bash
B=http://localhost:8000/api/v1
TOKEN=$(curl -s -X POST $B/auth/login -H 'Content-Type: application/json' \
  -d '{"identifier":"admin.demo@aapaatsathi.in","password":"Aapaat@2026"}' | jq -r .access_token)
A="Authorization: Bearer $TOKEN"
```

**Rehearsal rule:** scores drift with the simulator's hourly bucket, so the numbers below will move by a few points on the day. Read the live value out loud before you inject. Never say a number the screen is not showing.

### 3.1 Beat 1 — Ground truth outranks a stale gauge (~45 s)

Narrate: *"Kund, Rudraprayag district. Not a famous slide. Three neighbours, one crack."*

```bash
# state before
curl -s "$B/risk/leaderboard?limit=40" | jq '.wards[] | select(.code=="RPR-KND") | {score,level,crowd_uplift}'

# resident 1 reports anonymously; resident 2 and 3 report the same crack nearby -> auto-merge + corroboration
curl -s -X POST $B/reports -F hazard_type=landslide -F title="Crack above the school" \
  -F description="Opened overnight, four houses below it" -F latitude=30.5024 -F longitude=78.7507 \
  -F accuracy_m=12 -F self_severity=5 -F ward_code=RPR-KND -F lang=gar | jq '{code:.report.code,confidence:.confidence.value}'
curl -s -X POST $B/reports -F hazard_type=landslide -F title="Same crack from my side" \
  -F latitude=30.5038 -F longitude=78.7521 -F accuracy_m=15 -F self_severity=4 -F ward_code=RPR-KND -F lang=gar > /dev/null
curl -s -X POST $B/reports -F hazard_type=landslide -F title="Road is bulging too" \
  -F latitude=30.5011 -F longitude=78.7489 -F accuracy_m=20 -F self_severity=4 -F ward_code=RPR-KND -F lang=hi > /dev/null

# the sweep turns corroboration into an escalation
curl -s -X POST "$B/risk/sweep?broadcast=true&district=RPR" -H "$A" | \
  jq '{evaluated,created,suppressed,escalated:[.escalated[]|{ward,from,to,score,population_at_risk,reach}]}'
```

**On stage, point at four things:** the ward climbing yellow → orange on the map without a refresh (WebSocket `risk:update`); `crowd_uplift` hitting the **1.25 ceiling**; `created: 1` with `"from": "yellow", "to": "orange"`; and the reported `population_at_risk`.

Verified on this build: three corroborated reports moved RPR-KND from **58.41 (yellow, uplift 1.116)** to **65.41 (orange, uplift 1.25)**, and the next sweep auto-issued one alert with an `alert.auto_issued` audit entry.

Then prove the anti-noise rule, which is the best line in the demo — run the sweep again:

```bash
curl -s -X POST "$B/risk/sweep?broadcast=true&district=RPR" -H "$A" | jq '{created,suppressed}'
```

> "Same ward, still orange, `created: 0`. It escalated once and then shut up. Most warning systems fail the other way."

If `reach` comes back as `{"suppressed": ...}` instead of a send count, say so out loud: the in-process dedupe window already covered that ward and level — that is the same guard, working. A fresh boot normally shows real per-channel counts.

### 3.2 Beat 2 — A drill the operator controls (~40 s)

Narrate: *"Now the block officer wants to know what a real cloudburst does to Mussoorie. This is a what-if. It injects a hyetograph and it is tagged `scenario`, so a drill can never be mistaken for an observation."*

```bash
curl -s "$B/risk/leaderboard?limit=40" | jq '.wards[] | select(.code=="DEH-MUS") | {score,level}'

curl -s -X POST $B/risk/scenario -H "$A" -H 'Content-Type: application/json' -d '{
  "ward_code":"DEH-MUS","rain_1h_mm":120,"rain_24h_mm":260,
  "rain_72h_mm":360,"forecast_6h_mm":90,"soil_moisture":1.0,"broadcast":false
}' | jq '{score:.ward.score, level:.ward.level, p24:.ward.probability_24h, exposed:.ward.population_at_risk, note, top:[.ward.factors[]|{key,observed,contribution}]|sort_by(-.contribution)[:3]}'
```

Verified on this build: DEH-MUS Lalmati Tibba, Mussoorie goes from **yellow ≈56** to **red 82.72**, with **7,980 people exposed**, and the top three contributors are rainfall intensity, antecedent rain and the 6-hour forecast. The map cell turns red live.

Then the intelligence check — inject the identical rain into Binsar Ridge:

```bash
curl -s -X POST $B/risk/scenario -H "$A" -H 'Content-Type: application/json' -d '{
  "ward_code":"ALM-BSR","rain_1h_mm":120,"rain_24h_mm":260,
  "rain_72h_mm":360,"forecast_6h_mm":90,"soil_moisture":1.0,"broadcast":false
}' | jq '{score:.ward.score, level:.ward.level}'
```

> "Same storm, Binsar Ridge, 72 — orange, not red. The model refuses to evacuate a place the terrain does not warrant. Rain sets the trigger; the hillside sets the ceiling. That is also why we cannot just threshold rainfall, which is the first question I was hoping you would ask."

### 3.3 Beat 3 — Three languages, and a ledger that does not lie (~45 s)

```bash
# preview exactly what each language group receives, before sending anything
curl -s -X POST $B/alerts/preview -H "$A" -H 'Content-Type: application/json' \
  -d '{"ward_code":"DEH-MUS","hazard_type":"landslide","level":"red","broadcast":false}' \
  | jq '.messages | {en:.en.sms, hi:.hi.sms, gar:.gar.sms}'
```

Read the Garhwali line off the screen and translate it live — *"उंचाई मा जाव। बहंडो पानी स न जाव"* — "move to high ground, do not cross flowing water."

```bash
# author and broadcast for real (console provider -> simulated, never silently 'sent')
curl -s -X POST $B/alerts -H "$A" -H 'Content-Type: application/json' -d '{
  "ward_code":"DEH-MUS","hazard_type":"landslide","level":"red",
  "channels":["sms","ivr"],"broadcast":true,"ttl_minutes":90}' | jq '{code,level,delivered,reach_target}'

curl -s "$B/notifications/stats" -H "$A" | jq '{provider, simulated, by_status, by_channel, by_lang, note}'
```

Close the demo on the ledger, not on the map:

> "Provider `console`. Two thousand-odd messages, every one labelled **simulated**, zero labelled sent, because nothing left this machine. IVR fired only on the two highest levels — voice minutes cost money and only make sense when minutes matter. When a judge or a collector asks this system 'did you actually reach anybody', the answer is in a database table, and it is honest. **That** is the part we would defend hardest — not the model, the accounting."

### 3.4 Pre-computed fallbacks (if the live terminal fails)

Keep these in a browser tab as saved JSON responses; narrate over them and say plainly that the terminal is down.

| Fallback | Readiness source |
|---|---|
| Beat 1 escalation | `GET /api/v1/risk/history/RPR-KND` |
| Beat 2 red ward | `GET /api/v1/risk/leaderboard?limit=40` — PKR-RNK Ranikhot sits at **red 77.86**, uplift **1.25**, **5,530 exposed**, confidence 0.98, straight off a fresh boot |
| Beat 2 factor waterfall | `GET /api/v1/wards/PKR-RNK` → `factors[]` |
| Beat 3 trilingual copy | `GET /api/v1/alerts/live` → `localized` |
| Beat 3 ledger | `GET /api/v1/notifications/stats` from the boot sweep |

**If everything fails:** show Ranikhot. It is red on a cold boot, it is the most important ward in the deck, and it needs no interaction — open the factor waterfall and read ten lines aloud.

---

## 4. Likely judge questions — and our answers

Rules for Q&A: answer in three sentences or fewer. Volunteer the limitation before they find it. Never say "the model predicts". Never claim a user, a deployment or a partnership.

**1. IMD and SDMA already issue red alerts. Why is yours not just a duplicate?**
IMD forecasts the atmosphere; a district red alert is the correct statement about the sky over several thousand square kilometres. We do not compete with it — we consume it and translate it. The translation is from "this district" to "this ward, this hour, these forty families, on SMS in Garhwali." Our ten-factor model deliberately uses rainfall as an input, not as an answer: rainfall alone cannot tell you which of two wards in the same rain cell has a Siwalik toe undercut by a drain. Getting IMD nowcasts and CWC bulletins in as authoritative override inputs is roadmap item 3, not a competitive claim.

**2. What is your accuracy? Precision and recall?**
We do not have one, and we will not invent one. Accuracy requires a labelled event ledger with ward-level outcomes time-aligned to antecedent features; that dataset does not exist publicly for Uttarakhand. What we have is a defensible prior with every weight published and every contribution persisted. If we published a percentage today it would be a number from a fit against thin air, and a system that carries evacuation orders should not start that way. Section 7 of our disclosure document states exactly what we would need to produce one.

**3. Why hand-set weights instead of machine learning?**
Because the failure mode of a model that cannot explain itself is an inquiry commission asking why a ward was told to evacuate, and a boosted ensemble cannot answer that per ward, per hour. A transparent additive model with a persisted per-factor breakdown is auditable, and auditability is a hard requirement in this domain, not an aesthetic. If a labelled ledger appears, the right move is to fit weights and *then keep the breakdown* — the two are not mutually exclusive.

**4. False positives: what happens after you cry wolf six times in one monsoon?**
Three mechanisms, all in code. Alerts fire only on an **upward level transition**, so a ward hovering at 76 gets one alert, not one per sweep. A 90-minute dedupe window suppresses repeats. And a district engineer can retune weights and thresholds because they live in a versioned `RiskModelConfig` row, not in source. The false-alarm rate is exactly what a one-block pilot exists to measure — and our answer to "what is it today" is that we do not know yet.

**5. Who pays for SMS and voice at scale?**
Not a resident. Bulk transactional SMS in India runs at roughly paise per message and IVR at a few paise per minute, so a district-wide single-level escalation is a few lakh rupees per round, and a monsoon season is not a hundred rounds. That is a line item a district disaster authority or a sponsor's CSR allocation can carry, and it is the specific thing we are asking sponsors for on slide 11. Our default provider costs nothing, which is why the project is reviewable at all. Note also that voice is gated to orange and red only, so we are not paying to read out advisories.

**6. What happens when the network is down — which is exactly when these events happen?**
Partially handled, honestly: SMS and circuit-switched voice survive data blackouts that kill an app, which is the whole reason delivery is not push-based. But if the towers are down, we are down — that is a real limitation and it is in our submission document. The roadmap answers are reporting **in** by SMS from a feature phone, a store-and-forward retry queue with delivery receipts, and a radio link to the block control room. Anyone who tells you software solves a cut fibre is selling you software.

**7. How is this different from the NDMA app, the SAMDAN/Red Alert apps or existing state systems?**
Those are broadcast and smartphone-first: a citizen installs an app and receives zone or district messages. We are ward-first and non-smartphone-first — the output is a text and a phone call, not a screen someone has to open. We also expose an operator surface the broadcast apps do not: a triage queue, a scenario drill runner, a versioned model and a delivery ledger, which is what a district administration actually needs to run the thing. We are not claiming to have studied their internals; the architectural difference we can defend is granularity plus channel plus accountability.

**8. Your crowd reports are anonymous and anyone can file one. How do you stop manipulation?**
Bounded by design. Crowd input does not add to a score, it multiplies it, and the multiplier is hard-capped at **1.25×** by configuration — so a ward at 60 can reach 75, not 150. Uplift is earned by **independent** corroboration and reporter trust, not by volume: reports of the same hazard within 1.2 km in 48 hours merge into one rather than stacking, anonymous reporters start at a lower weight, and a staff dismissal subtracts 0.10 from that reporter's trust. Three neighbours with a real crack outrank a stale gauge; a coordinated forward cannot push a district into evacuation.

**9. Terrain data is seeded, so on what evidence should a collector trust a score?**
None yet, and we say so in the repository itself, in a `DISCLAIMER` constant and on the public model page. Slope, lithology, thrust distance, NDVI and population are realistic approximations, not surveyed values, and ward polygons are synthetic outlines. What a collector can trust today is the *method*: it is fully inspectable, the inputs are the standard ones the hazard literature agrees on, and the design is the one an agency can swap real layers into without rewriting anything. Our ask is a pilot with real layers, not a licence to run this on approximate data.

**10. Uttarakhand already has GSI landslide susceptibility maps and district hazard profiles. Why recompute?**
Because a susceptibility map is a static annual product and the trigger is hourly. Susceptibility is one of our ten factors — we consume that class of information as a prior and combine it with live rainfall, forecast, soil state and ground reports. The two are complementary: GSI says which slopes are fragile, we say which of them is loaded right now.

**11. Two students, a month. Is this maintainable by anyone after the hackathon ends?**
The maintenance surface is deliberately small: one Python process, one database, no trained artefacts to drift, weights held as data. The parts needing expert upkeep — recalibration and threshold review — are exactly the parts we are asking a domain reviewer to own, publicly. Everything is MIT with a documented cold boot from zero configuration, and the disclosure document lists every third-party component. If we vanish tomorrow, someone else can run it, which is the point of open-sourcing it during a build challenge.

**12. How many real residents have used it? What traction do you have?**
Zero. No ward has been warned and no resident has filed a report. The verification we do have is engineering verification: a cold boot with no configuration, and 61 end-to-end checks passing, including the negative ones — a responder cannot trigger a sweep, an anonymous user cannot reopen a closed road, self-registration cannot mint an administrator, and a physically impossible rainfall injection is rejected. Traction after a hackathon would be an unearned number.

**13. Did AI write this? (If asked.)**
Yes, with AI assistance, disclosed by tool and by role in `AI_AND_THIRD_PARTY_DISCLOSURE.md`. The problem selection, the ten factors and their weights, the uplift cap, the escalation-on-transition rule, the simulated-versus-sent ledger and the seed footprint are ours, and we can defend each. We reviewed every line that shipped.

**14. What did you build that you are most proud of?**
Not the map. The delivery ledger and the model page — the two pieces that make the system answerable. An early-warning tool that cannot say who it reached and why is a rumour with a UI.

---

## 5. Stage discipline

- **Numbers:** read them off the screen, never from memory. The simulator drifts hourly.
- **Language:** say "susceptibility prior" and "decision support". Never "predict", never "AI-powered", never "real-time forecast".
- **Names:** say Ranikhot, Dharali, Silyari, Karnaprayag, Chhilbikhuna, Mussoorie. Do not say "Zone A".
- **Honesty beats polish:** if a beat fails, name the failure and move to a fallback. A 2-person student team that debugs calmly on stage is a stronger sight than one that hides it.
- **Do not** claim IMD/SDMA/GSI/NDRF integration, partnership, endorsement or data access. Names in the seed data are realistic context; they are not agreements.
- **Do** hand a judge the disclosure document unprompted if the conversation reaches limitations. It is the most differentiated artefact we have; almost no other two-person entry will have written one.

# Idea Submission — Elite Coders CodeSprint 2026

**Team:** Ram + 1 (2 members)
**Project:** AapaatSathi (आपतसाथी) — ward-level landslide and flash-flood early warning for Uttarakhand's hill districts
**Category:** Web / Open Ended / Social Welfare

> Paste everything below the line into the idea field. ~600 words.

---

## A red alert for a district is not a warning for a hillside.

Uttarakhand does not lack disaster data. It lacks a warning that reaches the forty families living below one specific escarpment, in a language they read, on a phone that cannot run an app.

IMD and SDMA issue advisories at **district** scale. A hill district is thousands of square kilometres; a ward is a few hundred metres across. Nobody can evacuate "Pauri Garhwal." They can evacuate Ranikhot.

The cost of that mismatch is written down. In **August 2021** a slope failure at **Ranikhot** on NH-73 killed roughly fifty people — most of them pilgrims gathered on the runout zone below the slide. In **October 2021** a debris-laden flash flood on the Kalingjadh destroyed the markets at **Dharali** and **Silyara**. In **February 2021** the **Chamoli** disaster sent a wave of water and boulders past **Karnaprayag**, taking two hydropower projects. **Chhilbikhuna** in Almora slides every monsoon without exception. Each sat under a slope a ward-level system could have flagged hours ahead, inside a district already under an alert nobody below the escarpment acted on.

**AapaatSathi** scores landslide and flash-flood susceptibility per **ward**, every fifteen minutes, and delivers the result by **SMS and automated voice call in English, Hindi and Garhwali**. Three decisions make it different from another weather dashboard:

**1. Granularity with an audit trail.** A transparent additive model fuses ten weighted factors — rainfall intensity, 72-hour antecedent rain, soil saturation, a 6-hour forecast, slope, lithology, thrust-zone proximity, channel proximity, vegetation deficit and event history. Every score persists its full per-factor breakdown, so an official can be told *why* a ward scored 78, term by term. Warning systems get investigated after people die; a black-box score is a liability, not a feature.

**2. Bounded crowd truth.** Independent corroboration of a resident's report lifts a ward's score, but only by a hard-capped multiplier. Three neighbours confirming a fresh crack within an hour outrank a stale rain gauge; a single WhatsApp forward cannot push a district into evacuation. Alerts escalate only on a genuine level transition, so people are not trained to ignore them.

**3. Delivery that does not assume a smartphone.** Pluggable SMS and voice-call providers, localised advice, and a delivery ledger that records honestly who was reached and separates messages actually sent from ones simulated.

**What the MVP concretely does.** Live ward map and per-ward risk; hazard reporting with corroboration and staff triage; automatic escalation to SMS and voice calls on threshold crossing; nearest shelter with real free-space counts and road status; a district-admin console that drafts, previews in three languages and broadcasts warnings; a **what-if drill runner** that injects a synthetic cloudburst and watches a ward climb to red on screen; and a published model page exposing every weight and threshold.

**Feasibility in the 15 Oct – 15 Nov window.** This is not a cold start: the FastAPI backend, risk engine, alerting pipeline, trilingual delivery layer, a React + MapLibre citizen map, responder queue and district console, and an eight-district, forty-ward footprint of real Uttarakhand locations are already written and running, with 276 unit tests and 61 end-to-end checks passing. The month goes into the parts a demo cannot fake: replacing seeded terrain priors with public geospatial layers (SRTM/CartDEM slope, GSI lithology, Sentinel-2 NDVI), switching to a live weather feed, a public deployment, and testing the reporting flow with residents of a ward that has actually slid.

**What we are not claiming.** Nothing is deployed or field-validated. The model is a calibrated **susceptibility prior**, not a trained predictor — there is no ward-level, time-aligned Uttarakhand event ledger to train on, and inventing one would be worse than admitting the gap.

**Impact.** The pilot footprint already assembled models **210,200 residents across 40 real wards in eight districts** — about 126,660 reachable phone numbers. At roughly ₹1–2 per SMS, warning all of them costs a few lakh rupees per round: a line item a district disaster authority can carry. A system that buys one hillside two hours, on the phone its residents actually own, is worth building. We would like a month to prove it.

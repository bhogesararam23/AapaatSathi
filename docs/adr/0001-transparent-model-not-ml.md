# ADR 0001 — Transparent additive susceptibility model, not a trained predictor

**Status:** accepted
**Date:** 2026-09-27

## Context

The obvious move for a hackathon "landslide prediction" project is to fit a
classifier or a neural network and report an accuracy number. That would be
dishonest here, for a specific reason: there is no ward-level, temporally
aligned Uttarakhand event dataset to train on. India has thousands of recorded
slope failures, but they are not published as feature vectors matched to hourly
rainfall for the same polygon. Any model "trained" in a month would be fitting
noise and then presenting the result as validation.

The second constraint is operational. Disaster warnings are audited. When a
slope fails and people die, an inquiry asks why the system said what it said at
that hour. A gradient-boosted ensemble cannot answer that per ward, per hour.

## Decision

Use a **transparent additive model**: ten factors, each a piecewise-linear
interpolation of an observed value to `[0,1]`, multiplied by a published weight
summing to 1.0. Persist the full per-factor contribution on every run. Expose
weights and thresholds through `GET /api/v1/risk/model` and render them in the
UI as a "why this score" waterfall.

Weights and thresholds live in a `risk_model_configs` **table**, not in code, so
a district engineer can retune after a false-alarm streak and every change is
versioned and attributable.

## Consequences

**Positive**

- Every score is explainable to a resident, a judge and an inquiry commission.
- No dataset exists to be over-fitted, so no over-fitted metric can be
  accidentally or deliberately over-claimed.
- Weights are auditable and locally adjustable without a redeploy.
- Runs on a laptop in a district control room with no GPU and no model artefact.

**Negative**

- Ceiling on discrimination is lower than a genuinely trained model would have
  with real data.
- Hand-set weights encode judgement; they are defensible but not derived.
- Requires the honesty note in the UI, which is less impressive on a slide than
  "94% accuracy".

## Rejected alternatives

- **Train a classifier on synthetic events.** Circular: the labels would come
  from the same priors we are trying to test.
- **Wrap an LLM to "reason about risk."** Non-deterministic, unauditable, and
  the wrong tool for a numeric threshold decision that must repeat identically.
- **Ship the model as a black box and claim accuracy.** Would likely win the
  hackathon and would be disqualifying if examined.

## Path to a real model

The append-only `ward_risks` table plus verified `hazard_reports` is exactly the
instrumentation needed to build a labelled dataset over time. The intended
upgrade is to keep this scoring layer as the prior and calibrate a learned
residual against recorded events once a district has logged a monsoon or two.

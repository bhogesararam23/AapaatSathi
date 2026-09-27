# ADR 0003 — Simulated-by-default delivery, with a ledger that never lies

**Status:** accepted
**Date:** 2026-09-27

## Context

Early-warning systems are judged on reach: "we alerted 12,000 people." That
number is trivially fakeable, and in this domain a fake reach number is not a
harmless demo flourish — it is the metric an administration would use to decide
whether the system works, and it is the metric that would be quoted back after a
failure.

There is a second, mundane constraint: sending real SMS costs money and requires
credentials. A reviewer must be able to run the whole escalation path without
either, and a developer must not be able to accidentally message thousands of
numbers while testing.

## Decision

Delivery goes through a provider interface with three adapters:

| provider  | behaviour                                                    | status written |
|-----------|--------------------------------------------------------------|----------------|
| `console` | logs the message, contacts nothing, costs nothing (**default**) | `simulated`    |
| `twilio`  | real SMS and TwiML voice calls via REST                       | `sent`         |
| `msg91`   | real bulk SMS via the route Indian government deals use       | `sent`         |

Missing credentials fall back to `console` with a warning rather than throwing
at send time. Every attempt is persisted to `notifications` with provider,
reference, language, channel and error. The API and the console surface
`simulated` and `sent` as different words in different colours, and the
`/notifications/stats` note says explicitly how many were simulated.

Voice (IVR) is only attempted at orange and red: it costs real money per minute
and is the right tool for a household with no literate phone user, not for every
advisory.

## Consequences

**Positive**

- Clone-and-run with zero credentials and zero spend.
- No path by which a demo silently messages real residents.
- Reach claims are auditable, and the honest version is the easy one to produce.
- A judge can see the full escalation-to-delivery chain actually execute.

**Negative**

- The headline demo number is simulated, which is less impressive than an
  unqualified "12,000 alerted" — that is the point.
- Two more adapters to keep working against provider API changes.

## Rules for anyone extending this

- Never write `sent` for a message that a provider did not accept.
- Never resolve a recipient list to real numbers in a test.
- If you add a provider, add it to the status table above and to the smoke test.

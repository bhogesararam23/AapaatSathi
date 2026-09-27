# Security policy

AapaatSathi is infrastructure that sits between a monsoon and a village. Treat
bugs in it accordingly.

## What counts as a security issue here

Beyond the usual (auth bypass, injection, credential leak), these are security
issues in this project because they degrade trust in a warning:

- Any path that lets a non-official **issue or revoke** a public warning.
- Any path that lets one district admin act on another district's alerts.
- A **`simulated` delivery reported as `sent`**, or any reach number that cannot
  be traced to rows in `notifications`.
- Leaking a **reporter's identity or phone** onto a public feed, the citizen
  map, the WebSocket `public` channel, or the notifications list.
- A **language fallback that sends an English-only message** to a recipient who
  cannot read it, or a mistranslated advice string that under-states danger.
- Anything that makes escalation **silently stop firing** — for example reading
  prior state after the new score has already been persisted.
- Alert flooding: a way to generate repeated warnings for one ward inside the
  dedupe window, causing the community to stop paying attention.
- Uploaded hazard photos served in a way that discloses EXIF location beyond what
  the report already contains.

## How to report

Open a **private security advisory** on the repository rather than a public
issue. Include the reproduction, the affected endpoint or component, and what a
successful exploit would let an attacker do.

You should get an acknowledgement within 3 business days. Do not open a public
issue for these; a fix lands before disclosure.

For everything else — a broken layout, a confusing label, a flaky test — a
normal issue is welcome.

## What we will not treat as a vulnerability

- The system being wrong about a landslide. It is a susceptibility prior with
  hand-set weights and no field validation. Being wrong is a modelling problem,
  tracked under `docs/adr/0001-transparent-model-not-ml.md`.
- Weak default credentials in the seed data. `SEED_ON_STARTUP=true` and the demo
  accounts exist for reviewers; production requires `SECRET_KEY` to be set and
  seeding to be disabled. Say so in your deployment, but do not report it.
- Availability. This is not a hardened, redundant, SLA-backed emergency service.
  It must never be presented as one.

## Deployment checklist

- [ ] `SECRET_KEY` set to a long random value
- [ ] `DATABASE_URL` pointed at Postgres, not SQLite
- [ ] `SEED_ON_STARTUP=false`, demo accounts removed or all disabled
- [ ] `ENVIRONMENT=production` so HSTS is emitted and `/docs` is gated
- [ ] `CORS_ORIGINS` restricted to your actual frontend origin
- [ ] `SMS_PROVIDER` set with real credentials, or the UI still shows simulated
      delivery honestly
- [ ] `USE_LIVE_WEATHER=true` with real telemetry, and the seeded priors replaced
- [ ] HTTPS terminated in front of the app
- [ ] `notifications` and `audit_logs` access restricted to district staff, with
      phone numbers masked in list views

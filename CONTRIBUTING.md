# Contributing to AapaatSathi

Thanks for taking a look. This is a small open-source project with one hard
non-negotiable: **it must never overstate what it knows.** Everything below
follows from that.

## Getting set up

Two terminals, no Docker:

```bash
# terminal 1 — API on :8000
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload
```

```bash
# terminal 2 — web on :5173
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and http://localhost:8000/docs. The database creates
and seeds itself on first boot.

## Before you open a pull request

```bash
cd backend  && python -m pytest -q && python scripts/smoke_test.py
cd frontend && npm run typecheck && npm run build
```

CI runs exactly these. If they pass locally they pass in CI.

## Ways to help that are genuinely useful

1. **Replace the seeded priors with real data.** Terrain, lithology, NDVI and
   population in `backend/app/seed.py` are realistic approximations, not
   surveyed values. Wiring in GSI, Survey of India, Bhuvan or State DGRRM layers
   is the single highest-value contribution available. See issue template
   `data-integration`.
2. **Localise.** The message catalog in `backend/app/services/i18n.py` is a
   dictionary. Kumaoni, Nepali, Bengali and Lepcha are all missing and all
   needed. A Garhwali or Kumaoni speaker reviewing the existing strings is
   worth more than a code change.
3. **Accessibility.** This is used on cracked screens, in daylight, by people
   under stress, some of whom cannot read. Audit contrast, font scaling, screen
   reader labels and the IVR path.
4. **False-alarm analysis.** If you can reason about precision/recall trade-offs
   for evacuation orders, the thresholds in `risk_model_configs` need your help.
5. **Report a way the system could mislead someone.** This will be treated as a
   security issue (see `SECURITY.md`), not a low-priority bug.

## Conventions

**Python.** 3.11+. Type hints on public functions. `snake_case` modules,
`PascalCase` classes. Async throughout — a blocking call in a request path is a
bug. SQLAlchemy 2.0 style (`Mapped` / `mapped_column`). Docstrings explain *why*
a choice was made when it is not obvious; comments that restate the code are
noise.

**TypeScript.** Strict mode, `noUnusedLocals` and `noUnusedParameters` are on
and the build fails without them. Components are functions; no class components.
Types live in `src/api/types.ts` and mirror the backend schemas — if you change
a response shape, change both.

**Commits.** Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`,
`test:`, `chore:`. Imperative subject under 72 characters. Explain the *why* in
the body when the diff does not make it obvious.

## Design rules worth knowing before you start

- Role gates are `Annotated[User, Depends(...)]` aliases in `core/deps.py`.
  Returning a bare callable and using it as an annotation breaks Pydantic
  namespace resolution at import time.
- Escalation is decided by comparing against the level **before** new scores are
  persisted. Reading prior state after the write makes every escalation look
  like a no-op, and the system stops warning people silently.
- Auto-issued alerts must carry the level that triggered them.
- Every new outbound message type needs a status that distinguishes simulated
  from sent.
- The public WebSocket channel carries no personally identifying data.

## Scope

This project is a warning and coordination tool. It is not a replacement for
engineering assessment, and pull requests that add autonomous action — ordering
an evacuation, closing a road without a human, dispatching a team — will not be
accepted. The system proposes; a named official decides.

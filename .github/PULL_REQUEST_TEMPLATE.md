## What

One or two sentences on what this changes, and why it matters.

## Why

The problem being solved, in terms of the person using the system. Link issues
with `Closes #123`.

## How to check it out

```bash
# exact commands, including any env vars or seed steps
```

- [ ] `cd backend && python -m pytest -q`
- [ ] `cd backend && python scripts/smoke_test.py` (API running on :8000)
- [ ] `cd frontend && npm run typecheck && npm run build`
- [ ] Manual check described above

## Honest-claims review

Required. Tick every line that applies, and explain any that do not.

- [ ] No new number, metric or reach claim is presented without the code path
      that computes it
- [ ] Anything simulated, seeded or mocked is still labelled as such in the API
      response **and** the UI
- [ ] `simulated` was not written as `sent`, anywhere
- [ ] New outbound message types distinguish simulated from delivered
- [ ] Seeded or approximate data is not described as surveyed or official
- [ ] No accuracy, AUC or false-positive claim was added without a validation
      dataset to back it

## Security and privacy

- [ ] New endpoints declare a role gate, or are deliberately public and say why
- [ ] No reporter identity or phone number added to a public payload
- [ ] District admins remain scoped to their own district
- [ ] Nothing new is logged that could identify a resident

## Notes for review

Anything unusual, workarounds taken, or follow-ups you deliberately left out.

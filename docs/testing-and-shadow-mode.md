# Testing and Shadow Mode

## Test philosophy

The project uses controlled component tests to prove contracts, then relies on shadow mode to collect real household evidence. Synthetic cases are useful for plumbing; they are not a substitute for observing real behaviour.

## Important tests completed in Milestone 1

### Routine detector window
A known Wednesday routine was tested before, during and after its candidate window. The detector correctly produced candidates only in the bounded interval.

### Deterministic enrichment
A 15:30 synthetic state against a 15:14 routine with a 15:11-15:17 historical range produced:

```json
{
  "minutes_from_typical": 16.0,
  "outside_historical_range": true,
  "minutes_beyond_historical_latest": 13,
  "routine_confidence": "strong",
  "routine_recurrence": 1.0
}
```

### Fail-closed contract
A deliberately malformed routine candidate produced deterministic `ignore` with confidence `1.0` and model `deterministic-policy`. It did not reach Qwen.

### End-to-end evaluator
A valid candidate flowed through enrichment -> Qwen -> SQLite with `action_taken=false`.

### Autonomous runner
Two consecutive real cycles completed 60 seconds apart with zero candidates/evaluations and no errors. This proved FastAPI lifespan startup, continuous scheduling and clean service operation.

## Shadow data model

`attention_ledger` answers: **what situations exist?**

`attention_observations` answers: **how did Jarvis judge each situation over time?**

The second table is intentionally append-only so a progression such as `monitor -> interrupt` is not lost when the aggregate row updates.

## Useful commands

```bash
curl -s http://127.0.0.1:8000/observer/status | jq
journalctl -u jarvis-core --since "10 minutes ago" --no-pager
```

Inspect the shadow stores:

```bash
/opt/jarvis-core/.venv/bin/python scripts/inspect-shadow.py
```

## Before live actions

At minimum I want shadow evidence covering multiple detector families and enough real situations to review false positives, unstable judgements, repeated messages and capability hallucinations.

Strict Pydantic validation of model output and an explicit action-capability/policy layer are also prerequisites before any live notification path is introduced.

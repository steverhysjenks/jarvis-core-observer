# Testing and release

## Why the regression pack matters

Jarvis has several safety boundaries which are individually simple but important in combination. A change to activity detection must not silently break waste evidence, ledger identity, judgement validation or action gating.

The release process therefore treats regression as a gate rather than a final confidence check.

## 1.1.0 gate

Before the known-good internal `0.7.0` deployment was captured for this public 1.1.0 release, the complete standalone test pack reported **16 passed, 0 failed**:

- `test_actionable_routines.py`
- `test_activity_observer.py`
- `test_bin_evidence.py`
- `test_departures.py`
- `test_detectors.py`
- `test_enrichment.py`
- `test_evaluator.py`
- `test_evidence.py`
- `test_judgement.py`
- `test_judgement_matrix.py`
- `test_ledger.py`
- `test_observer.py`
- `test_routine_detector.py`
- `test_routines.py`
- `test_waste.py`
- `test_waste_detector.py`

The activity regression itself contains ten deterministic cases: tiny versus meaningful walk satisfaction, walking with children, constrained activity with children, unknown-family fail-closed behaviour, calendar-gap calculation, long contextual event handling and stable/different occurrence identity.

A real-context integration check then simulated a weekday lunchtime opportunity and proved detector → enrichment → required-facts validation without invoking Qwen or announcement delivery.

## Release sequence

```text
change
→ compile
→ regression pack
→ integration check
→ restart
→ /health
→ /observer/status
```

Runtime validation of the captured internal build returned version `0.7.0`; Observer was live on a 60-second interval with `last_error: null` after restart. The public repository then resets the version line to `1.1.0`, so a deployment from this repository should be validated again and should report `1.1.0`.

## Known test hygiene debt

The current tests are standalone Python scripts rather than a formal pytest suite. Some existing tests can touch the configured Jarvis SQLite path. Isolating every test into temporary storage is a future improvement and is listed on the roadmap.

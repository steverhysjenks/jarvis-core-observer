# Extracted production-test comparison (2026-10-14)

Source: read-only `jarvis-production-tests` extraction supplied by the operator. This is historical evidence of source used on LXC 122, not a fresh test-pass result. Bytecode/cache filenames indicate Python 3.13 and pytest 9.1.1 were used; cached bytecode alone does not prove successful test outcomes.

All 22 extracted Python sources already exist under `tests/regression/` and match after CRLF/LF normalization:

- test_action_executor.py, test_action_policy.py, test_activity_detector.py, test_areas.py
- test_availability.py, test_bounded_judgement.py, test_context_live.py, test_departure_behaviour.py
- test_detector_orchestration.py, test_enrichment.py, test_evaluator_integration.py, test_import_contracts.py
- test_judgement_contract.py, test_ledger_lifecycle.py, test_observer_cycle.py, test_observer_live.py
- test_qwen_live.py, test_replay.py, test_resolver.py, test_routine_math.py
- test_voice_routing.py, test_waste_detector.py

Missing production test sources: **none**. Substantively modified sources: **none**. Existing Git-only regression module: `test_isolation_guards.py`, retained unchanged. No source file was blindly overwritten and no extracted bytecode/cache was imported. New production profile/checks are additive.

## Configuration differences

| Setting | Extracted production | Existing offline Git CI |
| --- | --- | --- |
| Default collection | tests | tests/regression |
| Live/behavioural markers | Registered, not excluded | Registered and blocked before collection |
| addopts | -ra | strict markers; excludes live + behavioural; cache disabled |
| Async mode | Unspecified | strict |
| Isolation harness | No conftest included in extraction | Root conftest with reviewed allowlist, dummy service settings, audit guards and temporary SQLite |

The new explicit production profile has its own configuration/plugin/runner and does not change root pytest.ini or conftest.py. Original five Qwen behavioural executions (four parametrised work statuses plus one away/home case) remain excluded before collection. Existing isolation guards continue to run in offline CI; they are omitted from the real-environment production profile because they deliberately assert dummy/offline settings.

The explicit acceptance allowlist runs the 19 deterministic modules, two existing read-only live modules (nine tests), and the new six integration checks. Unreviewed files and behavioural-marked tests fail closed. All original extracted test sources remain available in Git, including excluded behavioural source.
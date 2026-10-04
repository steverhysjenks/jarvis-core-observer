# ADR-002: Deterministic qualification before probabilistic judgement

**Status:** Accepted

## Context

An LLM can judge nuance but should not infer facts or feasibility that can be established directly from authoritative context.

## Decision

Detectors, enrichment and deterministic validation establish whether a candidate is real and feasible. Only then may Qwen judge `ignore`, `monitor` or `interrupt`.

Qwen cannot override missing required facts, family constraints, calendar sufficiency, situation lifecycle or action policy.

## Consequences

More policy exists as explicit Python rather than prompt text. The model sees less context and has less freedom, but failures are easier to reason about and test.

# ADR 029: Policy Before Execution

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

Action execution occurs only after deterministic policy approval; executor has no authority to decide appropriateness.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

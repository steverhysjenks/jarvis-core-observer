# ADR 025: Situation Resolution Primary Anti Nag

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

Situation lifecycle/deduplication is the primary anti-nag mechanism; global cooldown is secondary.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

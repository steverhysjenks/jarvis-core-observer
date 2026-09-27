# ADR 028: Record Delivery After Confirmation

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

Persist successful announcement delivery only after the downstream Home Assistant action succeeds.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

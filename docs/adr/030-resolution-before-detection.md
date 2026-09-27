# ADR 030: Resolution Before Detection

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

Each observer cycle resolves existing situations before detecting and judging new candidates.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

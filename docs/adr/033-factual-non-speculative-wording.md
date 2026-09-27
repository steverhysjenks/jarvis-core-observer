# ADR 033: Factual Non Speculative Wording

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

Proactive wording reports observed conditions and does not infer intent, fault, forgetting, or require acknowledgement.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

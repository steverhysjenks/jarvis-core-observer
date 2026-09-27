# ADR 034: Configurable Runtime Safety Controls

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

Observer mode, interval and global announcement cooldown are runtime configuration, with shadow as the safe default.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

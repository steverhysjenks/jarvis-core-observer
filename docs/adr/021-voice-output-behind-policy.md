# ADR 021: Voice Output Behind Policy

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

Voice output is a separate action service behind deterministic policy; the LLM cannot address hardware directly.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

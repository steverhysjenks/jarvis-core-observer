# ADR 031: Strict Llm Output Contract

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

Treat model output as untrusted until strict schema and semantic validation succeeds; failures become non-actionable.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

# ADR 032: Capability Safe Announcements

**Status:** Accepted  
**Date:** 2026-09-27

## Decision

The model may only propose short informational announcements within explicitly available capabilities.

## Rationale

This preserves the Jarvis Core boundary between deterministic evidence/policy and probabilistic judgement, keeps proactive behaviour explainable, and fails closed when evidence or capabilities are insufficient.

## Consequences

The observer remains conservative by design. Additional capabilities must be explicitly modelled and policy-gated rather than inferred by the language model.

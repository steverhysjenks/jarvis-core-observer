# ADR-003: Semantic media requests use retrieval-grounded execution

**Status:** Accepted

## Context

Natural music requests need semantic interpretation, but allowing an LLM to invent catalogue objects or browse the entire library creates an unnecessary execution boundary.

## Decision

Semantic intent is bounded by Jarvis policy. Music Assistant remains authoritative for catalogue identity, genres, similarity and playback. Playable URIs come only from grounded MA retrieval.

## Consequences

Supported semantic concepts are intentionally finite. Adding a new mood/activity requires explicit policy or retrieval support, but execution remains explainable and testable.

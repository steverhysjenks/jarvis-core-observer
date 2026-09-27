# ADR: Consume Recorder History Through Home Assistant

**Status:** Accepted

## Context

This decision emerged during Milestone 1 of Jarvis Core while moving from reactive Home Assistant/LLM interactions to proactive observation.

## Decision

Keep raw telemetry owned by HA and consume selected history through its API rather than MariaDB.

## Consequences

This keeps responsibilities explicit, reduces hidden coupling and gives later milestones a stable boundary to evolve from. Where the decision adds implementation work, that cost is accepted in exchange for clearer evidence, safer behaviour and easier diagnosis.

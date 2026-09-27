# ADR: Routine Confidence Uses Opportunities and Consistency

**Status:** Accepted

## Context

This decision emerged during Milestone 1 of Jarvis Core while moving from reactive Home Assistant/LLM interactions to proactive observation.

## Decision

Routine confidence is based on recurrence across opportunities, temporal consistency and corroborated observations, not sample count alone.

## Consequences

This keeps responsibilities explicit, reduces hidden coupling and gives later milestones a stable boundary to evolve from. Where the decision adds implementation work, that cost is accepted in exchange for clearer evidence, safer behaviour and easier diagnosis.

# ADR: Separate Explicit Knowledge from Learned Behaviour

**Status:** Accepted

## Context

This decision emerged during Milestone 1 of Jarvis Core while moving from reactive Home Assistant/LLM interactions to proactive observation.

## Decision

Known household rules should be represented directly rather than statistically relearned.

## Consequences

This keeps responsibilities explicit, reduces hidden coupling and gives later milestones a stable boundary to evolve from. Where the decision adds implementation work, that cost is accepted in exchange for clearer evidence, safer behaviour and easier diagnosis.

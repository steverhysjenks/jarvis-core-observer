# ADR: Corroborated Physical Departure Observations

**Status:** Accepted

## Context

This decision emerged during Milestone 1 of Jarvis Core while moving from reactive Home Assistant/LLM interactions to proactive observation.

## Decision

Prefer front-door use plus person/geofence transitions over raw geofence transition alone for physical departure timing.

## Consequences

This keeps responsibilities explicit, reduces hidden coupling and gives later milestones a stable boundary to evolve from. Where the decision adds implementation work, that cost is accepted in exchange for clearer evidence, safer behaviour and easier diagnosis.

# ADR-005: Preserve UNKNOWN and fail closed where feasibility depends on it

**Status:** Accepted

## Context

A missing entity/state is not equivalent to `False`. Treating unknown child presence as “children are not with me” could incorrectly qualify constrained activities.

## Decision

Context builders preserve unknown state. Deterministic policy fails closed when feasibility depends on that state. Explicit exceptions may opt out: Walking is allowed with children, so family availability is informational rather than required for Walking.

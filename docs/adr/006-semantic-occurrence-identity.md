# ADR-006: Use semantic occurrence identity for proactive lifecycle

**Status:** Accepted

## Context

Observer recomputes candidates frequently. Volatile values such as remaining free minutes change every cycle and must not create a new ledger occurrence.

## Decision

Candidate keys represent the semantic occurrence. Activity identity uses activity type, day type, learned typical time and occurrence date, not the changing free-time window.

## Consequences

Announcement deduplication and resolution can operate on the real situation rather than on a snapshot of its current measurements.

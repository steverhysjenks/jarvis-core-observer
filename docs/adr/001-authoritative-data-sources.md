# ADR-001: Keep domain data in authoritative sources

**Status:** Accepted

## Context

Jarvis can see Home Assistant state, calendars, Garmin activity and Music Assistant catalogue/playback data. Copying all of this into Jarvis would create competing sources of truth and make behaviour harder to inspect outside the application.

## Decision

Home Assistant, Garmin and Music Assistant remain authoritative for their domains. Jarvis reads and correlates them. Jarvis persists only state that belongs to Jarvis itself, currently situation lifecycle and delivery history.

Garmin history is represented durably through a Home Assistant calendar rather than a Jarvis activity database.

## Consequences

Source availability and retrieval health matter. Analysis may need to be rebuilt on each cycle/request. In return, domain data stays visible, reusable and independently correctable.

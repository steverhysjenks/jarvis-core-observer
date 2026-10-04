# Data ownership and authoritative sources

One of the easiest ways to make Jarvis difficult to reason about would be to copy everything it sees into its own database and slowly forget which copy is authoritative.

1.1.0 deliberately does not do that.

## Principle

**Keep behavioural/domain data in authoritative sources. Jarvis consumes and correlates it. Persist only state that is genuinely Jarvis-owned.**

## Current ownership

| Information | Authority | Why |
|---|---|---|
| Entity/home state | Home Assistant | HA already owns the state machine |
| Current room | Bermuda through HA | room presence is a presence-system fact |
| Calendar commitments | HA calendars | calendars remain user-visible and independently useful |
| Garmin activity | Garmin, represented durably in HA calendar | activity should remain visible outside Jarvis |
| Music library/playback | Music Assistant | MA owns catalogue identity and queues |
| Situation status | Jarvis ledger | only Jarvis knows whether it has announced/resolved a candidate |
| Delivery history | Jarvis | only Jarvis knows exactly what it delivered |

## Garmin is the useful example

The first temptation was to give Jarvis its own activity database. I rejected that. Garmin is already the activity source and Home Assistant provides a useful durable calendar representation. The HA calendar is both machine-readable and visible to me.

Jarvis therefore reads `calendar.garmin_activities`, analyses it and discards the analysis when the request/cycle is complete. It does not maintain a competing historical activity store.

## Current state versus historical evidence

A related pattern is emerging for location:

- live HA entities are best for **where am I now?**;
- selected HA calendar/history evidence can be useful for **where was I / what pattern exists?**;
- Jarvis correlates the two.

Durable zone/location history is a roadmap item in 1.1.0, not a delivered claim.

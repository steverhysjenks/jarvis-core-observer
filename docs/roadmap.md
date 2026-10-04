# Roadmap after 1.1.0

This file separates ideas from delivered functionality.

## Context-aware delivery

Observer should continue to decide **whether** something is worth communicating. A separate delivery policy should decide **where/how** to communicate it.

The intended direction is home + stable room → EchoMuse voice; away/Work → Home Assistant mobile notification; no suitable route → defer/suppress. This is not implemented in 1.1.0.

## Location history / zones

Live HA zone state is useful current context. Selected durable location history could explain learned behaviours such as a lunchtime walk at Work. A machine-oriented HA calendar is a likely source because it preserves the authoritative-source pattern without putting another location database inside Jarvis.

## Better calendar semantics

The current activity detector uses a bounded blocking-calendar heuristic. Real commitments have semantics: a child activity may or may not consume my time, an all-day event is often context, and location matters. Availability should eventually combine commitment, location, family context and learned behaviour rather than reduce every event to busy/free.

## Activity improvements

- per-calendar retrieval health;
- learned activity similarity rather than the provisional 50% duration rule;
- activity-specific resolution when the opportunity expires or is completed;
- broader behaviours as evidence becomes sufficient.

## Observer efficiency

Consider avoiding repeated Qwen judgement for an occurrence which lifecycle already proves cannot announce again, while preserving correct monitor/resolution behaviour.

## Test isolation

Move runtime/database-sensitive tests to isolated temporary storage and consider a conventional test runner while keeping deterministic boundary tests.

## Version management

Replace the three current version literals in `app/main.py` with one authoritative application version.

## Music

- multi-room/group playback;
- extend an active session to additional rooms;
- Follow Me playback using stable Bermuda presence and preserved queue/position;
- listener-aware policy;
- richer history/favourites weighting;
- dynamic target discovery.

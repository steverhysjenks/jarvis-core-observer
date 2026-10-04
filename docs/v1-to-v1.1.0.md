# From V1 (1.0.0) to Jarvis Core 1.1.0

## The short version

V1 solved a routing problem. 1.1.0 is solving an intelligence problem.

The original project was a working multi-LLM voice router for Home Assistant. It proved that I did not need one model to do everything. Home Assistant native intents could handle deterministic commands, a small local model could handle cheap/general requests, a larger desktop model could be selected for HA-aware work, and a cloud model could handle current/external information. `jarvis-route` made the semantic choice; LiteLLM exposed model aliases; Home Assistant was deliberately called again so the chosen conversation agent retained its own tools and permissions.

That architecture was useful, but it was reactive. Nothing happened until I asked a question.

Jarvis Core grew from the next question: **if Home Assistant already knows a lot about what is happening, can Jarvis notice something useful without turning the house into a collection of noisy automations?**

## Side-by-side

| Area | V1 | Jarvis Core 1.1.0 |
|---|---|---|
| Primary purpose | Route an inbound voice request | Context, bounded capabilities and proactive intelligence |
| Trigger | User request | User request **or** Observer cycle |
| Deterministic first step | HA native intents | Context/detectors/capabilities/policy |
| LLM role | Classify L/D/C and downstream conversation | Narrow judgement after deterministic qualification |
| Home Assistant | Voice/tool authority | Authoritative home/context source and action boundary |
| State | Mostly request/route state | Situation lifecycle + delivery history |
| Presence | Useful to downstream HA | Bermuda room stability gates proactive speech |
| Music | Downstream conversation/tool problem | First-class bounded Music Assistant capability |
| Replay | Not a platform capability | Deterministic replay of exact recent delivery |
| Behaviour | Routing rules | Learned departures/routines and activity pattern |
| Historical activity | None | Garmin → HA calendar → learned pattern |
| Family constraints | None | Explicit context with UNKNOWN/fail-closed semantics |
| Testing | Boundary-by-boundary route verification | 16-script regression release gate + integration checks |

## What I kept from V1

### LiteLLM is still not the semantic router

That distinction remains important. LiteLLM is an API/model gateway. A model gateway should not quietly become the place where household policy, presence, behavioural evidence and action safety live.

### Home Assistant remains authoritative for Home Assistant

V1 called HA again after route selection because the selected conversation agent owned its tools and entity exposure. 1.1.0 extends the same philosophy: HA remains the source for home state, calendars, Bermuda-derived presence and other household facts. Jarvis consumes those facts rather than copying the whole home into its own database.

### Prove boundaries independently

The build approach is still the same: prove the source, prove the adapter, prove the deterministic policy, prove the LLM boundary, then compose them. That is why the current code is split into context, behaviour, detectors, enrichment, judgement, policy and action rather than one large agent prompt.

## What changed architecturally

### 1. Jarvis gained its own application boundary

`jarvis-core` is a FastAPI service with an authenticated request endpoint, context APIs, Observer status, notification history and replay. It has a systemd lifecycle and a small SQLite store for Jarvis-owned lifecycle.

### 2. Requests gained bounded capabilities

The capability dispatcher offers a request to explicit capabilities in order. Replay and music can claim a request. If neither claims it, the request remains available to the wider semantic path.

The important detail is `claimed` versus `handled`: once a bounded capability recognises that a request belongs to its domain, it owns the result even if policy prevents execution. That avoids an unauthorised or invalid music request accidentally falling through to a general LLM and being reinterpreted.

### 3. Observer became a real runtime

Observer builds a snapshot of user, home, family, calendar, recent semantic history and waste context. Detectors turn those facts into candidate situations. Enrichment attaches the facts required to make the candidate safe to judge. Missing evidence does not become a convenient `False`.

### 4. The LLM moved behind deterministic qualification

Qwen receives a bounded candidate only after required facts exist and deterministic validity passes. Its output is validated to a strict judgement contract: ignore, monitor or interrupt. Model/network/schema failure becomes a deterministic ignore, not an action.

This is a major difference from “give the model all my entities and ask it what to do”.

### 5. Action policy became a separate safety boundary

An `interrupt` judgement is still not permission to speak. Live mode, candidate lifecycle, already-announced state, global cooldown, primary-user home state, Bermuda source, room stability and explicit voice endpoint must all pass.

### 6. Jarvis gained delivery memory without becoming the source of truth for everything

The situation ledger and delivery history are legitimately Jarvis-owned. Garmin activity is not. Music catalogue identity is not. Calendar commitments are not. That ownership boundary is now deliberate.

## Functional evolution

### Music

The music work proved another important pattern: semantic does not have to mean unbounded. Jarvis can understand “something relaxing”, “90s rock”, “while I’m working” or “like Queen”, but Music Assistant remains the authority for what actually exists. Bounded policy maps supported moods/activities to approved catalogue genres; MA supplies grounded tracks and similarity relationships; playable URIs never come from the LLM.

### Replay and notification history

Once Jarvis could proactively speak, “repeat that” became a platform problem rather than a conversational trick. Delivery history records the exact message and route. Replay retrieves the last eligible proactive delivery and says the same thing again through the current voice endpoint.

### Learned activity

Activity intelligence is the defining 1.1.0 addition. A 90-day Garmin history is represented in a Home Assistant calendar. Jarvis analyses the real observations, qualifies stable patterns and can recognise a current opportunity. Calendar space, current home state, family feasibility and meaningful completion of the same behaviour are deterministic inputs. Qwen judges the value of interrupting; it does not decide whether childcare makes an activity possible.

## Why 1.1.0?

The original repository is the **V1 / 1.0.0 baseline**. The work since then is substantial, but it is still an evolution of the same Jarvis architecture rather than a replacement platform. For the public repository, versioning therefore continues from that baseline: **V1 becomes 1.0.0 and this release becomes 1.1.0**.

The earlier `0.7.0` number was useful while Jarvis Core was being developed privately, but carrying it into the public repository would make the project appear to have gone backwards from V1. The public release line is reset here and should continue forward from **1.1.0**.

The original V1 router should therefore be read as the **foundation and first architectural chapter**, not as an obsolete implementation that 1.1.0 pretends never existed.

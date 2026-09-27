# Development Journey

This is the part I usually find most useful when I come back to a project months later: not just what the final code does, but why it ended up this way.

## 1. Starting point - reactive Jarvis

I already had a working Home Assistant voice stack with EchoMuse, local Qwen, LiteLLM and `jarvis-route`. That solved request routing, but everything still began with me speaking or an HA automation firing.

The question for this project was different: **can Jarvis notice something before I ask?**

## 2. A separate Core service

I chose a dedicated Debian LXC rather than burying proactive reasoning inside Home Assistant. HA remains the source of truth; Jarvis Core becomes a consumer/orchestrator.

The final LXC is VMID 122. An early attempt used 118 before I remembered Proxmox VMIDs are cluster-wide and the secondary node already owned it.

## 3. Context before intelligence

The first useful endpoints were deliberately boring: home mode, primary-user context, calendar context and semantic history.

That established an important boundary: the LLM should not receive a giant entity dump. Python and HA integrations should convert raw infrastructure into stable meaning first.

## 4. Presence taught us to respect existing abstractions

Bermuda already solves BLE room presence. Rebuilding that from proxy-distance entities inside Jarvis would create two competing truths. Jarvis therefore consumes Bermuda's area/floor/distance output.

PIR/mmWave are valuable but answer a different question: "is there activity here?" They cannot answer "is Steve here?" in a house with children and cats.

## 5. History became semantic

HA Recorder history initially looked straightforward, but several details mattered:

- the first returned record is a baseline state;
- start/end windows need to be explicit;
- door activity alone does not identify who used the door;
- named HA zones are richer than a binary home/not_home model.

The history layer therefore emits semantic events rather than exposing raw state transitions to higher layers.

## 6. Learning routines without pretending they are facts

Departure observations are built from corroborated physical evidence. Routines are then clustered by weekday/time and scored using recurrence across opportunities, temporal consistency and corroboration.

The key lesson was that four samples are not automatically a strong routine. Four observations across four opportunities are much more meaningful than four observations across twenty opportunities.

## 7. The first Judge was given too much responsibility

The first Qwen matrix was the turning point.

I gave the model context and a routine candidate and expected it to work out whether the current time was early/late, whether the user was home and whether calendar evidence increased urgency.

It produced plausible prose, but some factual reasoning was wrong or inconsistent.

Instead of adding a bigger prompt, I narrowed the model's job.

Python now derives facts. Qwen judges attention.

This is probably the most important architectural decision in Milestone 1.

## 8. Bins proved this was not just a departure project

I deliberately moved to a different use case: bin collection.

The collection schedule already exists as HA calendars. The household rule is that bins can go out from 19:00 the previous evening. Entrance history can provide weak evidence that I may not have done it.

This introduced three concepts that departure learning did not:

- explicit household knowledge;
- scheduled events;
- absence-of-event evidence.

It also exposed the rule that absence is only meaningful when the observation window is valid and the source was available.

## 9. Shadow mode became a first-class feature

Once the Judge could return `interrupt`, I did not connect it to EchoMuse. Instead I added a persistent ledger.

That immediately paid off: Qwen proposed a message offering to "send a message to your office", despite no such capability existing. In a live agent that would be a capability hallucination. In shadow mode it is simply useful evidence for the next design iteration.

## 10. Autonomous, but unable to act

The final step in this milestone was the background Observer loop, attached cleanly to FastAPI lifespan.

It wakes every 60 seconds. When nothing is interesting, it does not call Qwen. When there is a candidate it can evaluate and persist it, but `action_taken` remains false and there is no action implementation available.

That is where this repository snapshot is taken.

## What I learned

The project has ended up looking less like "put an LLM in Home Assistant" and more like a small event/context architecture:

- source systems retain ownership;
- semantic adapters hide infrastructure details;
- deterministic code establishes facts;
- probabilistic models make bounded judgements;
- persistence provides auditability;
- action is a separate policy boundary.

That feels much closer to the kind of architecture I actually want to build - and, usefully, much closer to the solution-architecture/SRE thinking I use professionally than I expected when I started playing with local voice assistants.

# ADR 012: Bounded movie identity through Jellyfin, playback through HA

Status: Accepted and deployed. Decision recorded 1 November 2026, reconciled with the deployed BOF-86 design on 9 November 2026.

## Context

Jarvis must distinguish film from music across shared Assist satellites, resolve real catalogue identities and support hands-free playback from TV standby. Router owns unclaimed conversational routing. Home Assistant owns device state and service calls. The production release uses one Core worker.

## Decision

Core owns film and generic media selection within its capability dispatcher. HA Assist supplies the canonical conversation ID and origin through Router. Explicit movie/film or TV requests select video, and explicit music retains the established Music Assistant path. Generic play and put on compare both catalogues before execution. A missing or incomplete catalogue is uncertainty. The video destination defaults to the living-room TV independently of the originating satellite. Music uses the existing room-aware speaker selection.

When both catalogues match, ask for the type before playback. Authenticated HA users can answer within 60 seconds in the same canonical conversation and origin. Shared satellites require a fresh explicit request because their device identity does not identify the speaker. Fresh explicit requests are independent of a pending choice. The selected candidate is checked again before execution. Punctuation immediately after an explicit film qualifier is accepted as grammar. Punctuation within the title remains title data.

Jellyfin owns film identity. Use a bounded, scoped HTTPS lookup for an exact title and optional year, a local movie source and a numeric TMDB ID. A root-owned snapshot provides bare-title ownership hints, including subtitle roots, but cannot replace live identity resolution. Exact-title ambiguity requires clarification and an absent original cannot resolve to a sequel.

Use fixed HA device entities and the existing Sony-triggered Apple TV/Infuse wake automation. HA media-player state is primary. Only fresh contradictory plug power evidence vetoes an otherwise reported Sony standby. Core waits for device readiness and uses the configured HDMI input. Prepare stays read-only. Under the accepted MR !28 policy, a resolved play request authorises replacement of previous playback. Send one internally constructed Infuse TMDB deep link when needed and allow only evidence-gated Select or Play. Video verification requires authoritative content identity and advancing position.

Keep the existing Router deadline handshake for cold execution. Core creates a durable uncertainty hold before the first mutation and uses bounded in-memory receipts to suppress duplicates. An unresolved hold blocks further play until the operator reconciles the exact operation. Ordinary traffic and read-only prepare retain their existing budgets. The separately installed HA integration reserves media search for Jarvis, preserves native state delegation and is excluded from Core packages.

## Consequences and limits

The same resolved film can launch from either satellite without changing the video target. Assist can finish before a bounded Core cold-start operation returns. Physical playback can succeed while HA lacks the telemetry required to verify it. Those outcomes remain uncertain and retain the hold. A restart clears in-memory choices and receipts but preserves the durable marker. Physical device state can change between the last read and a command. Automated retries and compensating device actions are excluded.

The [video runbook](../video-playback.md) records configuration, deadlines, the authorised reconciliation procedure and the five-pass, one-failure physical campaign. The initial ready-only policy and fixed recognition aliases were superseded by the merged cold-start and catalogue changes.

## References

- [ADR 003: grounded media](003-retrieval-grounded-music.md)
- [MR !28: authorised playback orchestration](https://gitlab.boffjenkins.co.uk/homelab/jarvis-core-observer/-/merge_requests/28)
- [MR !31: Core media coordination](https://gitlab.boffjenkins.co.uk/homelab/jarvis-core-observer/-/merge_requests/31)
- [BOF-86 physical acceptance](https://linear.app/boff-jenkins-projects/issue/BOF-86#comment-53d81a59-032f-43cf-926c-956241fa0bf5)

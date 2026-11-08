# ADR 012: Bounded movie identity through Jellyfin, playback through HA

Status: Proposed — offline implementation for BOF-86; merge, deployment and live acceptance are separate approvals.

Date: 1 November 2026.

## Context

Core and Router production reconciliation is accepted. Core release is `d6d9c09147e198d8233ceb5fdb3c0132e1220da3-20261101T121515Z-bfadbe9a`; Router's generic named-domain envelope already owns unsuccessful claimed capabilities without L/D/C fallback. Music, nutrition, Mealie and Observer must retain their boundaries. The Apple TV and Sony TV are in use; this implementation has no permission to contact them or execute live HA actions.

## Decision

Register a deterministic `video` capability after replay/nutrition/Mealie and before music. Require a TV target or explicit movie/film grammar for arbitrary titles. Three recognition-only aliases support bare Forrest Gump, KPop Demon Hunters and Shawshank Redemption; they confer no catalogue identity. Only an anchored television destination suffix is removed, preserving titles containing “on”. Explicit music grammar and unknown bare play remain with music. Generic nutrition follow-up matching excludes recognised video without changing dispatcher order or discarding nutrition continuity. Claimed invalid, disabled and failed video requests remain video-owned.

Jellyfin owns movie identity. Use one authenticated HTTPS GET against a configured existing user and movie-library UUID, at most 12 records and 256 KiB, with no redirects or ambient proxies. Require an exact normalised title, optional year, one local movie record, media-source presence and authoritative numeric TMDB provider ID. Remakes, duplicate editions, incomplete metadata and truncated searches cannot be auto-selected. No new model, database, guest or credentials are commissioned by this change.

HA remains the device boundary. Fix Apple TV to `media_player.living_room_3` and Sony to `media_player.sony_kdl_55w905a`; accept no request-supplied entity IDs, service names or URLs. Construct only `infuse://movie/<verified-TMDB-ID>?play` internally. The sole mutation is Apple's HA `media_player.play_media` with content type `url`. No power, source selection, pause, stop, seek, remote, automation or script invocation exists. The existing Sony source label must be configured and both devices already ready. Prepare means resolve catalogue identity and inspect readiness, without opening Infuse or sending a playback command. Physical film staging is deferred.

Treat an on TV as possibly occupied even if HA reports no title. Require the exact phrase “confirm video takeover” in the same origin/user/conversation/satellite/listener context within 60 seconds. Re-resolve the catalogue and compare viewing identity/source before consuming approval, then sample once more immediately before the command. Approval is single-use and is invalidated by a changed item, state, app, source or configuration. Plain yes is not video consent. Stable conversation identity is required to approve takeover. The HA agent forwards and returns the canonical chat-log ID, including when the raw caller ID is absent. Mocked two-turn HA-agent/accepted-Router-contract/Core tests cover confirmation and cancellation; physical EchoMuse continuity is unverified. Core packaging does not install this integration source: a separate approved HA integration rollout is required before enablement.

Serialize this capability in-process and bound each request, including lock wait and dependencies, to 12 seconds (below Router's existing 20-second Core timeout). Do not retry or schedule actions. Cache up to 128 request receipts for five minutes, rejecting conflicting reuse; fail closed on capacity. Duplicate responses are explicitly historical receipts (`fresh_verification=false`), never a new playing/prepared claim. A possibly sent command sets an uncertainty latch before the await. Timeout, cancellation, failed verification or service error leaves it latched and blocks further play attempts pending operator reconciliation. Cancellation propagates and awaited work is unwound; no background tasks are created.

Report playing only after two HA samples show Infuse, the exact constructed TMDB content identity, the correct powered TV/input, playing state and increasing media position. Service success or app launch alone is not proof. Missing telemetry produces uncertain, never success. HA's observed states are the available evidence, not an atomic transaction with physical controls.

## Consequences and limits

### 6 November 2026 bounded title-recognition amendment

The owner authorised replacing fixed bare-film aliases with scoped catalogue-derived ownership. An explicitly refreshed root-owned title snapshot supplies exact title names and subtitle-colon roots, without media identities or credentials. A subtitle root recognises intent but never resolves an absent original to its sequel. Live exact title/year/TMDB lookup remains the identity authority. This supersedes only the original fixed-alias requirement. Existing dispatcher order, explicit music/typed nutrition precedence, disabled-mode no-network behaviour, takeover, deadlines and fail-closed verifier are retained. See the dated commissioning amendment in `docs/video-playback.md` for snapshot bounds, refresh and cold-start limitations. Valid punctuation is permitted while URLs, paths, controls and compound commands remain rejected. No Infuse-version logic or telemetry fallback is introduced.

`VIDEO_ENABLED=false` by default, checked at capability entry before any catalogue or HA access. No production configuration changes are part of this MR. Existing physical viewing is unaffected by this development session. All orchestration tests use mock HA clients under the repository's mandatory network/process audit hook. Linux Python 3.13 CI is authoritative; Windows async event loops require sockets prohibited by that hook.

The in-memory lock, confirmation and duplicate receipts assume the existing single application worker. They are not durable across restart and cannot coordinate multiple workers or external HA users. The uncertainty latch has no automatic reset or expiry; a later operator reconciliation is needed. Restarting must never be used as an automatic retry/reset. Same request IDs are deduplicated only within the receipt window; no exactly-once claim spans a restart. A physical user can act between the last sample and command; this race is unavoidable with the existing HA API and remains an acceptance risk.

Actual HA/Infuse telemetry may not expose the TMDB deep link or frequent position updates, in which case the strict success verifier will intentionally fail. The user physically confirmed a Forrest Gump launch on 1 November via `infuse://movie/13?play`. Reported HA observations were idle then playing, Infuse, title Forrest Gump, duration 8525, position 0 unchanged, no film content ID, and Sony on HDMI 1. Offline fixtures preserve this evidence and return uncertain. Installed Infuse version and its Now Playing API setting remain explicitly UNVERIFIED as of 5 November. Firecore documents an opt-in API from Infuse 8.5.9 with mDNS discovery and read-only `/nowplaying`, including TMDB identity and position, but no update-cadence guarantee. No trusted adapter/endpoint is verified or implemented. These unknowns do not block disabled-feature merge; authoritative identity and actual progress within the bounded deadline remain mandatory before enablement. Infuse library mode and Jellyfin-to-Infuse mapping still need acceptance. The existing turn-on/Infuse-launch automation is neither invoked nor changed; external interactions require physical acceptance. No wake/source automation is added as a workaround. See [video runbook](../video-playback.md) for the explicit live-acceptance gate.

### 7 November 2026 cold-start amendment

The owner requires play to start from standby. The preceding ready-only decision is superseded for play. Core uses the existing Sony wake service and waits for the existing Sony-triggered Apple TV and Infuse automation. An existing plug power reading corroborates assumed Sony standby. Correct input, idle playback and the bounded wake budget gate the single movie command. The same uncertainty latch now covers wake and input selection. Prepare remains read-only. See the [video runbook](../video-playback.md) for the detailed gates and timeout budgets.

### 8 November 2026 TV power-state amendment

Home Assistant media-player entities provide primary state. When Sony reports off, Core reads the paired plug once as corroboration. Only a valid, fresh reading above 5 W vetoes wake. Stale or unavailable meter readings leave the HA device states in control. Core rechecks device state and automation activity before wake, and still requires observed readiness after wake. Unknown or unavailable media-player states block execution.

## References

- [ADR 003: grounded media](003-retrieval-grounded-music.md).
- [Jellyfin Items controller and user/library filters](https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/ItemsController.cs).
- [Firecore TMDB deep links and optional play parameter](https://support.firecore.com/hc/en-us/articles/215090997-API-for-Third-Party-Apps-Services).
- [HA Apple TV deep links through play_media](https://www.home-assistant.io/integrations/apple_tv/#launching-apps).

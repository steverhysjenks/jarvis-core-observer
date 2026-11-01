# ADR 012: Bounded movie identity through Jellyfin, playback through HA

Status: Proposed — offline implementation for BOF-86; merge, deployment and live acceptance are separate approvals.

Date: 1 November 2026.

## Context

Core and Router production reconciliation is accepted. Core release is `d6d9c09147e198d8233ceb5fdb3c0132e1220da3-20261101T121515Z-bfadbe9a`; Router's generic named-domain envelope already owns unsuccessful claimed capabilities without L/D/C fallback. Music, nutrition, Mealie and Observer must retain their boundaries. The Apple TV and Sony TV are in use; this implementation has no permission to contact them or execute live HA actions.

## Decision

Register a deterministic `video` capability after replay/nutrition/Mealie and before music. Require a TV target or explicit movie/film grammar for arbitrary titles. Two recognition-only aliases support the requested bare Forrest Gump and KPop Demon Hunters examples; they confer no catalogue identity. Unknown bare play remains with music. Claimed invalid, disabled and failed video requests remain video-owned.

Jellyfin owns movie identity. Use one authenticated HTTPS GET against a configured existing user and movie-library UUID, at most 12 records and 256 KiB, with no redirects or ambient proxies. Require an exact normalised title, optional year, one local movie record, media-source presence and authoritative numeric TMDB provider ID. Remakes, duplicate editions, incomplete metadata and truncated searches cannot be auto-selected. No new model, database, guest or credentials are commissioned by this change.

HA remains the device boundary. Fix Apple TV to `media_player.living_room_3` and Sony to `media_player.sony_kdl_55w905a`; accept no request-supplied entity IDs, service names or URLs. Construct only `infuse://movie/<verified-TMDB-ID>?play` internally. The sole mutation is Apple's HA `media_player.play_media` with content type `url`. No power, source selection, pause, stop, seek, remote, automation or script invocation exists. The existing Sony source label must be configured and both devices already ready. Prepare means resolve catalogue identity and inspect readiness, without opening Infuse or sending a playback command.

Treat an on TV as possibly occupied even if HA reports no title. Require the exact phrase “confirm video takeover” in the same origin/user/conversation/satellite/listener context within 60 seconds. Re-resolve the catalogue and compare viewing identity/source before consuming approval, then sample once more immediately before the command. Approval is single-use and is invalidated by a changed item, state, app, source or configuration. Plain yes is not video consent. Stable conversation identity is required to approve takeover.

Serialize this capability in-process and bound each request, including lock wait and dependencies, to 12 seconds (below Router's existing 20-second Core timeout). Do not retry or schedule actions. Cache up to 128 request receipts for five minutes, rejecting conflicting reuse; fail closed on capacity. A possibly sent command sets an uncertainty latch before the await. Timeout, cancellation, failed verification or service error leaves it latched and blocks further play attempts pending operator reconciliation. Cancellation propagates and awaited work is unwound; no background tasks are created.

Report playing only after two HA samples show Infuse, the exact constructed TMDB content identity, the correct powered TV/input, playing state and increasing media position. Service success or app launch alone is not proof. Missing telemetry produces uncertain, never success. HA's observed states are the available evidence, not an atomic transaction with physical controls.

## Consequences and limits

`VIDEO_ENABLED=false` by default, checked before every dependency access. No production configuration changes are part of this MR. Existing physical viewing is unaffected by this development session. All orchestration tests use mock HA clients under the repository's mandatory network/process audit hook. Linux Python 3.13 CI is authoritative; Windows async event loops require sockets prohibited by that hook.

The in-memory lock, confirmation and duplicate receipts assume the existing single application worker. They are not durable across restart and cannot coordinate multiple workers or external HA users. The uncertainty latch has no automatic reset or expiry; a later operator reconciliation is needed. Restarting must never be used as an automatic retry/reset. Same request IDs are deduplicated only within the receipt window; no exactly-once claim spans a restart. A physical user can act between the last sample and command; this race is unavoidable with the existing HA API and remains an acceptance risk.

Actual HA/Infuse telemetry may not expose the TMDB deep link or frequent position updates, in which case the strict success verifier will intentionally fail. The exact installed app versions, Infuse library mode, Jellyfin-to-Infuse mapping, source label and HA attribute shapes remain unverified. No wake/source automation is added as a workaround. See [video runbook](../video-playback.md) for the explicit live-acceptance gate.

## References

- [ADR 003: grounded media](003-retrieval-grounded-music.md).
- [Jellyfin Items controller and user/library filters](https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/ItemsController.cs).
- [Firecore TMDB deep links and optional play parameter](https://support.firecore.com/hc/en-us/articles/215090997-API-for-Third-Party-Apps-Services).
- [HA Apple TV deep links through play_media](https://www.home-assistant.io/integrations/apple_tv/#launching-apps).

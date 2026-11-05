# BOF-86 video capability — offline implementation

Development only. Do not merge, deploy, enable, run the application against live configuration or invoke any media command without separate approval. The Apple TV and Sony television were in use during implementation. No live service calls, device reads, scripts, automations or delayed commands are needed to run the reviewed tests.

## Request contract

Existing path: HA Assist → Router `/route` → authenticated Core `/request` → capability dispatcher. Router's accepted generic capability response supports `domain=video`, `handled`, `speech`, `operation_status` and `continue_conversation`; no Router change is required. The included HA agent correction uses `chat_log.conversation_id` for forwarding and both success/error replies, rather than the possibly absent raw caller ID. This integration source is not installed by Core packaging; its separate approved HA integration rollout is an enablement prerequisite. Video is registered before music/semantic fallback and after replay/nutrition/Mealie.

Examples:

| Request | Extraction |
|---|---|
| Play Forrest Gump on the living room TV. | play; Forrest Gump; living room |
| Ask Jarvis to play KPop Demon Hunters. | play; KPop Demon Hunters; sole configured living-room target |
| Get Forrest Gump ready on the TV. | prepare; Forrest Gump; living room |
| Play the movie Dune (2021) on the TV | play; Dune; 2021; living room |

Trailing four-digit years are also supported. Only an anchored television destination suffix is stripped: On the Waterfront and The Girl on the Train retain their titles. Forrest Gump, KPop Demon Hunters and Shawshank Redemption are recognition-only bare aliases. Explicit song/track/album/artist/playlist/music requests remain with music. A pure video-recognition guard excludes explicit video requests and takeover phrases from generic pending nutrition follow-ups without reordering capabilities or consuming the nutrition draft. Arbitrary titles need “movie”, “film” or an explicit TV target; unknown bare play requests stay with existing music routing. Only living room/living_room/lounge are allowed room aliases. An explicit target overrides origin; otherwise the supplied origin area must be supported, or absent origin selects the sole configured room. Unsupported rooms, compound actions and URLs fail closed when claimed. No film IDs are embedded in recognition aliases.

Every enabled request needs a request ID; Router already supplies one. Duplicate IDs within the same context return a historical receipt without another command or fresh playback check (`already_processed`, or `uncertain` for an uncertain original, with `fresh_verification=false`); reuse for different text/area is rejected. Keep a stable origin, user identity and conversation ID for takeover confirmation. User context is supplied by the existing authenticated Router/HA path, not independently authenticated by this capability. Generic yes is not video confirmation and retains existing routing.

Results always include domain video, handled boolean, bounded_video path, speech, operation_status and structured result. Disabled, ambiguous, not_found, unsupported_room, invalid_request, confirmation_required/expired, state_changed, request_conflict, busy, unavailable and uncertain stay claimed. Prepared means catalogue identity and TV readiness checked with no launch. Playing means verified playback, not just a successful service call.

## Catalogue and configuration

See `config/jarvis.env.example`. Keep `VIDEO_ENABLED=false`. No live secrets are added or changed by the MR.

A later approved commissioning session must identify the existing Jellyfin HTTPS URL, user UUID, movie library UUID and appropriate read-only catalogue token from authorised sources. Do not assume an unrelated token is interchangeable or create one during this work. Tokens go only in the X-Emby-Token header, not URLs, diagnostics or fixtures. TLS validation stays enabled. User/library filters narrow requests; an administrator API key may have broader upstream privileges, so do not claim these filters enforce server-side least privilege.

One movie search uses title, optional year, library/user, Movie type, provider/media-source fields and a 12-record cap. Results are exact-matched; ambiguous remakes or duplicate files require a more precise title/year or separate catalogue cleanup. No fuzzy identity inference, pagination follow-up, provider-ID invention or arbitrary edition selection. Missing TMDB IDs, virtual/unavailable records, malformed or oversized results fail closed.

Configure `VIDEO_TV_SOURCE` only after verifying the existing Sony input label. Fixed entity IDs are Apple TV `media_player.living_room_3` and Sony `media_player.sony_kdl_55w905a`. No caller-supplied device target or URL is executed.

## Prepare, play and occupied viewing

Prepare performs catalogue lookup and up to three readiness samples. It changes no device state and does not open the details screen. Physical film staging is DEFERRED; prepared is only a read-only catalogue/readiness result. The TV must already be on the configured input and Apple TV ready; there is no wake-up or source selection implementation.

An on TV is conservatively occupied even when HA cannot identify viewing. Play requests therefore normally return a takeover prompt. To approve, say “confirm video takeover” within 60 seconds in the same stable conversation. Confirmation is single-use, context-bound and cancelled by “cancel video takeover”, a replacement video request, expiry or changed evidence. Catalogue identity and relevant viewing attributes are rechecked. No command is sent if they change.

Only after approval and final state comparison does Core send one `media_player.play_media` request with an internally constructed `infuse://movie/<TMDB-ID>?play` link. No retry, remote command, seeking, source/power change or script/automation invocation exists. All work shares a 12-second deadline; there are no orphaned or delayed playback tasks.

Success requires Infuse app, exact selected TMDB content link, playing state, correct TV source and increasing position across samples. If HA reports only a friendly title or insufficient position updates, the result is uncertain. Do not relax this to successful app launch. A possibly delivered command latches the capability against further play commands until an operator inspects reality. Do not automatically stop playback or issue compensating actions; those could disrupt someone else's viewing.

## Playback evidence and verification gap — 5 November 2026

The user reports a successful, physically confirmed Forrest Gump launch on 1 November using `infuse://movie/13?play`. Sony was on `HDMI 1`; Apple TV transitioned from idle to playing with app Infuse, title Forrest Gump, duration 8525 seconds and position 0 unchanged across available readings. No film-identifying `media_content_id` was exposed. The fixture records only those reported fields. This session did not repeat that command. Execution worked; authoritative automated verification remains unresolved, so these observations produce `uncertain` and latch further playback attempts.

**Installed Infuse version: UNVERIFIED. Now Playing API setting: UNVERIFIED.** The reported Apple device software version is tvOS, not Infuse. Firecore documents an opt-in Now Playing API in Infuse 8.5.9+, discovered through `_infuse-np._tcp.local` with its advertised port, and read-only `GET /nowplaying`. Documented fields include state, positionSeconds, durationSeconds and item identity fields such as tmdbID. No refresh-cadence guarantee establishes compatibility with the 12-second Core / 20-second Router budgets. The existing HA adapter supplies HA states/services, not this API; no trusted Now Playing adapter or endpoint has been verified or added. Version, setting, endpoint, identity and timely actual progress must be examined during separately approved physical acceptance. Their current unknown status does not block review/merge with video disabled, and does not justify title-only verification, extrapolated progress or enablement.

The existing Infuse launch automation reacts to Apple TV remote turn-on, calls Apple TV turn-on, waits two seconds, selects Infuse, then waits three seconds. It does not map Sony inputs. This capability neither invokes nor alters it and issues no turn-on/source command; external automation/CEC interactions still require controlled physical observation.

## Offline validation

Run existing protected development CI validation/regression on the focused branch. `conftest.py` sets dummy endpoints and video disabled before imports, admits only reviewed test modules and blocks network, DNS, processes and production SQLite access through a non-removable audit hook. Catalogue HTTP tests use httpx MockTransport; HA orchestration tests use mock clients. The in-process `/request` test does not run ASGI lifespan or Observer. Two-turn tests execute the actual HA agent method with mocked HA interfaces, a SHA-256-pinned copy of the accepted Router response renderer and mapped mock transport into real Core ASGI. They start with raw incoming conversation ID absent and use the canonical chat ID for confirmation/cancellation while a nutrition draft remains pending. This is offline contract evidence, not execution of the complete HA framework/Router server or physical EchoMuse continuity. Realistic idle/playing fixtures deliberately lack content identity and advancing position; no successful HA playback telemetry is fabricated.

The Linux Python 3.13 runner executes the full existing suite, isolation guards and controller tests. No CI workflow/environment annotations or deployment rules are changed. Feature branches cannot package/deploy through the protected-main jobs. Local Windows static/pure tests are useful, but its async loop needs loopback sockets rejected by isolation; do not weaken guards to run them. Tests must never use real HA/Jellyfin configuration or target a real server as a connectivity check.

## Separate controlled physical acceptance proposal — NOT executed

1. Obtain explicit approval naming both living-room devices and a test window after viewers release them. Confirm separately approved deployment/config enablement, healthy baseline, exact package, retained rollback and recoverable state backup. No delayed testing based on presumed availability.
2. Read actual HA/Infuse versions, Now Playing API setting, source label and telemetry shape only within that authorisation. Separately approve/install the canonical-conversation HA integration correction and verify physical EchoMuse second-utterance continuity. Verify the approved Jellyfin credentials and unique movie/TMDB identity. Confirm Infuse contains the same item. No assumption that a TMDB details page proves local media availability.
3. With video disabled, verify the request remains video-owned through Assist → Router → Core and returns disabled without HA commands. Recheck music/nutrition/Mealie/replay and unrelated L/D/C through safe contracts.
4. After explicit enablement approval, run prepare; prove no device/service mutation. Test unavailable/off/wrong-input outcomes without adding wake/source automation.
5. In an approved occupied-viewing scenario, verify the prompt sends zero commands; reject cross-user/conversation confirmation, expiry and changed viewing. Verify cancellation is read-only. Do not interrupt genuine viewing to stage this test.
6. After explicit playback permission, confirm one selected film and observe exactly one bounded HA command. Verify item identity, app, actual playback progress, audible/visible result and duplicate-request suppression. Record whether HA exposes the required content ID; absence is a blocker, not permission to weaken verification.
7. Use isolated mocks for transport timeout/outage/malformed responses; do not stop HA, Router, Core or other production dependencies to induce failures. If a live command has uncertain outcome, stop issuing commands and inspect with the operator.
8. Recheck Observer progression, authentication, persistent state and neighbouring capabilities. Stop at any failed gate; do not enable video generally or send additional playback without the agreed acceptance decision.

## Deployment, rollback and open gates

No deployment/enablement is authorised by this MR. A later approved rollout must use fresh exact-main validation/packaging, existing manual production gates, preflight and release receipt. No schema changes or runtime dependency additions are introduced. Keep existing configuration/state external and preserve the accepted baseline release as rollback target.

Disablement is VIDEO_ENABLED=false through the existing separately authorised configuration procedure; recognise that changing service environment may require an approved restart. Code rollback uses the existing Core release lock, verified previous symlink target, service restart and health/Observer acceptance procedure in [cd.md](cd.md). Neither code rollback nor disablement recalls an already sent media command or restores physical viewing. No automatic stop/source/power compensation is included.

Open gates: reviewed MR and passing exact-HEAD CI; actual Jellyfin credential/library mapping; installed Infuse deep-link support and library mode; exact Sony input label; stable HA conversation identity; actual content-ID/position telemetry; explicitly approved deployment, enablement and physical acceptance. Receipt/confirmation state is memory-only and bounded to five minutes/60 seconds; it does not survive restart or coordinate multiple workers. Do not reset an uncertainty latch by automatic restart or retry. See [ADR 012](adr/012-bounded-video-through-jellyfin-and-ha.md).

Broader group SSH variable retirement remains PARKED. Runner, credentials, Router, LiteLLM, live HA and infrastructure are unchanged. Only the repository HA integration source is corrected; it has not been installed.

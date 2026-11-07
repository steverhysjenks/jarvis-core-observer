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

### Catalogue-derived bare titles — 6 November 2026 amendment

Bare film recognition now uses `VIDEO_TITLE_INDEX_FILE`, a root-owned `root:jarvis` mode `0640` JSON snapshot at `/etc/jarvis-core/video-catalogue-titles.json`. This supersedes the fixed recognition-alias description above: there are no film-name allowlists in application code. The snapshot is scoped to the configured Jellyfin user/library UUIDs and contains complete catalogue titles, not playback identity or permission. Exact titles and the part before a subtitle colon establish ownership only. An absent original with an indexed sequel subtitle remains `not_found`; the sequel is never substituted. Sequels with different exact titles are not ambiguous; same-title remakes or duplicate editions remain ambiguous.

Refresh explicitly under the existing configuration/release lock: load the existing protected catalogue settings in an authorised diagnostic process, call `JellyfinClient.title_index()` and atomically write its result with the ownership/mode above. This is one GET for the configured Movies library, capped at 10,000 records / 8 MiB / the existing four-second HTTP timeout, with no redirects, ambient proxies or pagination. Incomplete, empty, oversized or wrong-type results must not replace an index. No background refresh, new service or CI workflow is introduced. The local index is capped at 2 MiB and 10,000 names. Verify its scope and recognition before enabling video. Keep it outside code releases; refresh when library titles change. New/unindexed films still need explicit movie/film/TV grammar until refreshed.

The index permits disabled-mode ownership without contacting Jellyfin or HA. A previously valid index is retained in memory on read/parse failure only for the same configured file/user/library; a cold start with an absent/invalid index cannot infer bare-film ownership. Keep video disabled until configuration/index validation passes. A stale ownership hint never allows playback: the existing bounded exact-title/year lookup, valid media source and numeric TMDB identity remain mandatory for every operation. Explicit music grammar wins, unknown bare requests retain music routing, and generic nutrition follow-ups defer to indexed video without changing typed-nutrition precedence or dispatcher order. Cross-domain bare names remain inherently contextual; use explicit song/artist/movie grammar where a music name is also a catalogue film title.

Punctuation such as colons, apostrophes, commas and internal periods is title data. URLs/schemes, paths, control characters, semicolons and compound actions remain claimed-invalid for explicit video; no caller text is executed or used as a playback URL.

The observed catalogue fixture records the three owned Moana films (2016, 2024 sequel, 2026 remake) and Top Gun: Maverick (2022). Original Top Gun (1986) is expected not-found, not an acceptance failure. Actual film names/IDs occur only in evidence/tests, never the recognition implementation. One logical Movies library may contain several physical folders; folder count is not a blocker.

Before a deployment restart, reconcile any previous uncertain launch with the operator's physical observation, privately back up configuration and explicitly disable video under the existing lock. Record that restart clears memory-only receipts/latch; never use it as a silent retry. Keep video disabled for this correction's deployment and read-only acceptance. Do not issue any media-device command or automatically resend a previous launch. The existing takeover, deadline and authoritative playback verifier are unchanged.

See `config/jarvis.env.example`. Keep `VIDEO_ENABLED=false`. No live secrets are added or changed by the MR.

A later approved commissioning session must identify the existing Jellyfin HTTPS URL, user UUID, movie library UUID and appropriate catalogue credential from authorised sources. Do not assume an unrelated token is interchangeable. Tokens go only in the supported `Authorization: MediaBrowser Token="…"` header, not URLs, diagnostics or fixtures. Jellyfin 12 removed the legacy `X-Emby-Token` mechanism. TLS validation stays enabled. User/library filters narrow requests; an administrator API key may have broader upstream privileges, so do not claim these filters enforce server-side least privilege.

Store the credential using the existing root-owned secret-file convention: `/etc/jarvis-core/secrets/jellyfin-catalogue.token`, owner `root:jarvis`, mode `0640`, referenced by `JELLYFIN_TOKEN_FILE` in the protected environment file. A configured file takes precedence over the legacy `JELLYFIN_TOKEN` environment value; missing, unreadable, invalid UTF-8 or empty files fail closed without fallback. Never put a real credential in Git, a command argument, a URL or a report. Environment-value changes use the established release lock, private configuration backup, single-service restart and health/Observer verification procedure. Keep `VIDEO_ENABLED=false` during catalogue commissioning. Credential rotation is a separate operator action and must not be claimed complete merely because authentication works.

One movie search uses title, optional year, library/user, Movie type, provider/media-source fields and a 12-record cap. Results are exact-matched; ambiguous remakes or duplicate files require a more precise title/year or separate catalogue cleanup. No fuzzy identity inference, pagination follow-up, provider-ID invention or arbitrary edition selection. Missing TMDB IDs, virtual/unavailable records, malformed or oversized results fail closed.

Configure `VIDEO_TV_SOURCE` only after verifying the existing Sony input label. Fixed entity IDs are Apple TV `media_player.living_room_3` and Sony `media_player.sony_kdl_55w905a`. No caller-supplied device target or URL is executed.

## Prepare, play and occupied viewing

Prepare performs catalogue lookup and up to three readiness samples. It requires an awake Apple TV and Sony on the configured HDMI input. It makes no service calls.

Play resolves the exact film before accessing the TV. For a cold start Core sends Sony one `media_player.turn_on`. When Sony reports assumed off, the existing TV and Apple TV power meter must corroborate standby with a reading of 0–5 W reported within three minutes. Missing, stale or higher readings stop the request before power-on. The threshold is specific to this paired plug and conservatively excludes observed active viewing and higher standby readings.

Sony's off-to-on transition triggers the existing **Wake Apple TV and Launch Jellyfin** automation. It wakes Apple TV and opens Infuse. Core waits for that run to finish and Apple TV to report idle, then selects the configured Sony HDMI input once if needed. Sony's slow standby poll may require one read refresh. With Sony already on the correct HDMI input and Apple TV off, Core can wake Apple TV directly while the automation is idle. Correct input and idle playback must be observed before launch.

Playing, paused or opaque Apple TV state requires the existing takeover confirmation. Sony playing/paused and stale assumed-on Sony evidence are also treated as occupied. A pre-existing wrong Sony input stops the request. Confirmations still bind the same movie, viewing fingerprint, source and conversation for 60 seconds. A change during wake stops the operation before the film command.

Play has an 18-second total budget inside Router's 20-second timeout, with at least four seconds reserved after wake for launch and verification. Prepare and confirmation retain their 12-second budget. Core sends one validated `infuse://movie/<TMDB-ID>?play` link. Any uncertain wake, input selection or launch latches further playback until operator reconciliation. The HA automation may finish its own started run after Core's deadline.

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

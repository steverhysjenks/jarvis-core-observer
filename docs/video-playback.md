# BOF-86 video playback runbook

## Request path and ownership

EchoMuse transcribes through HA Assist. The installed Jarvis conversation agent forwards the canonical conversation ID and origin through Router /route to authenticated Core /request. The agent reserves native media search for Jarvis, delegates HassGetState to Home Assistant and preserves local-first controls. Router returns claimed capability responses, including failures. Unclaimed requests continue through the existing routing. The HA integration is maintained separately from the Core package. See [Assist intent ownership](bof86-assist-intent-ownership.md).

The satellite area identifies the request origin and remains available to Music Assistant for room-aware speaker selection. Video defaults to the living-room TV from any supported entrypoint, including Office and Kitchen. An explicit TV destination must name the living room or a supported alias such as lounge. Unsupported video rooms return a claimed error.

| Request | Meaning |
| --- | --- |
| Play The Goonies | Check both media catalogues before selecting a capability |
| Put on Descendants | Same arbitration, with the living-room TV as the film destination |
| Play the movie, Babe | Explicit film; the comma after the qualifier is a separator |
| Put the film Top Gun: Maverick on | Explicit film; the colon inside the title is preserved |
| Play the artist Queen | Explicit music; use existing Music Assistant targeting |
| Get Forrest Gump ready on the TV | Resolve the film and inspect readiness without sending device commands |

Explicit movie/film or TV phrasing selects video. The parser accepts a comma, colon, en dash or em dash immediately after the film qualifier. Internal title punctuation is preserved. Optional years disambiguate remakes. Only a terminal TV destination is removed, so titles such as On the Waterfront retain their wording.

For generic play, Core compares scoped Jellyfin results and exact Music Assistant library candidates before playback. A unique match from one catalogue can execute when the other has ruled out a match. Missing or incomplete evidence is uncertainty. Multiple film editions require a title/year. If both media types match, Core asks for a choice before sending commands. An authenticated HA user can answer within 60 seconds in the same canonical conversation and origin context. A shared satellite, including one carrying a device account, requires a fresh explicit request naming the media. A short reply such as "the film" cannot authorise execution from a shared satellite. An independent explicit request can proceed while a choice is pending. Identity is checked again before executing a selected candidate.

## Catalogue and configuration

Jellyfin is the film identity authority. Requests use verified HTTPS and the configured user and Movies library UUIDs. Lookup is bounded to a four-second HTTP timeout, 12 results and 256 KiB with no redirects or ambient proxies. Playback requires one exact normalised title/year match, a local media source and a numeric TMDB provider ID. Missing films return video not_found for explicit requests. A missing original is never silently replaced by its sequel. Multiple physical folders can belong to one logical Movies library.

Keep secrets in the protected root-owned /etc/jarvis-core/secrets/jellyfin-catalogue.token file (root:jarvis, mode 0640) configured via JELLYFIN_TOKEN_FILE. A configured file takes precedence over the legacy environment value and fails closed if unusable. The client sends Authorization: MediaBrowser Token="..." and keeps certificate validation enabled. User/library filters scope the lookup; upstream key privileges are managed by Jellyfin.

The optional VIDEO_TITLE_INDEX_FILE at /etc/jarvis-core/video-catalogue-titles.json supplies scoped recognition hints, including subtitle roots. It grants no playback authority. Refresh under the release lock using JellyfinClient.title_index() and atomically write a complete result as root:jarvis mode 0640. Refresh reads only the configured library, caps the response at 10,000 records and 8 MiB, and does not replace the index with an empty, incomplete or invalid result. Core accepts up to 2 MiB and 10,000 names locally. The last valid in-memory index is reused only for the same file/user/library scope. Live resolution still verifies the exact identity.

VIDEO_ENABLED defaults to false in source and is enabled in the accepted production configuration. Config and credentials live outside release packages. Disabled explicit video requests are claimed without Jellyfin or HA access. Use the [Core CD procedure](cd.md) for release operations and keep production configuration and state external.

## Playback and verification

1. Resolve the requested film first. Core reads Apple TV media_player.living_room_3 and Sony media_player.sony_kdl_55w905a. VIDEO_TV_SOURCE is the configured Sony HDMI 1 label. Unknown or malformed device states stop execution.
2. If Sony reports off, Core checks the paired power meter once. A valid reading above 5 W reported within 180 seconds vetoes standby. Stale, missing or invalid readings do not override the HA state. Core rechecks the devices and wake automation before mutation.
3. Core powers Sony on once when needed. Sony's state transition triggers the existing **Wake Apple TV and Launch Jellyfin** automation, which wakes Apple TV and opens Infuse. Core waits for the automation to finish, wakes Apple TV if still off, and selects the configured HDMI only if needed. Core confirms stable device state and an idle wake automation before launch.
4. A resolved play request authorises replacement of existing playback on this TV under the MR !28 policy. Ambiguous media still requires an explicit selection before execution. Core opens the selected TMDB deep link once unless the requested film already appears to be playing. A changed, stable paused target can permit at most one contextual Select and one Play. No repeated launch or blind follow-up is issued.
5. Verified playing requires Infuse, exact TMDB content identity, the correct TV input and increasing playback position. App launch, title and playing state can corroborate physical success but cannot establish verified identity and progress. A possibly delivered operation without sufficient verification returns uncertain.

Prepare resolves the title and checks readiness without power, source or Infuse commands. Normal Router requests have a 20-second transport timeout. Core budgets 18 seconds for ready-state play and 12 seconds for prepare. A cold request receives a mutation-free deadline offer and Router sends the same request ID once with the extended budget. Core allows 44 seconds and reserves the last six seconds for dispatch and verification. Router waits up to 50 seconds. Assist can end the spoken turn earlier.

## Reconciliation and rollback

Core writes /var/lib/jarvis-core/video-uncertain before the first media mutation. A possibly delivered command without strict verification leaves this marker in place across service restarts and release activations. Further play is blocked while read-only prepare remains available. In-memory receipts suppress duplicate execution for five minutes and do not survive restart. The marker is the durable safeguard.

1. Stop attempts after uncertain. Correlate the request ID and receipt with HA automation traces and the Sony, Apple TV and Infuse state. If telemetry lacks identity, ask the operator what is physically visible.
2. Verify that the exact operation has terminated and no commands or automation remain active. If either is unproven, preserve the hold.
3. Obtain explicit authorisation to reconcile that operation and restart only jarvis-core. Under the existing Core deployment lock, verify the release, process and marker identity. Preserve the marker as video-uncertain.reconciled-<request-id> before removing the active marker and restarting. Restore the hold if restart fails. Verify Core health, live Observer progression and the active marker state. Keep the archive as incident evidence.
4. Treat any subsequent playback as a new, separately authorised request. Device cleanup is separate and limited to the completed test's playback.

For code rollback, use the retained release and health checks in [Core CD](cd.md). A release restart does not recall sent commands or undo physical effects. Before rollback to a version predating the durable hold, disable video through the approved configuration procedure. Where both Core and Router are involved, roll Core back before removing Router's extended deadline support.

## Acceptance and operating limits

The [MR !31 interactive campaign](https://linear.app/boff-jenkins-projects/issue/BOF-86#comment-53d81a59-032f-43cf-926c-956241fa0bf5) finished with five passes and one failure.

| Case | Recorded physical result |
| --- | --- |
| R01 Office, The Goonies | Correct film played from standby. HA showed playing 36.9 seconds after transcription. |
| R02 Kitchen, Descendants | Correct film played from standby. HDMI 1 at 23.1 seconds and Infuse playing at 34.6 seconds. |
| R03 Office, Babe | Film/music ambiguity was reported. A short shared-satellite reply started neither. |
| R04 Office, explicit Babe | Failed. Whisper produced "Play the movie, Babe" and Jarvis fell through. The separator correction is covered by offline parser and Assist/Router/Core regressions. |
| R05 Office, Queen | Music Assistant played on the originating Office speaker only. |
| R06 Kitchen, Friday the 13th | Expected film not_found with no device wake. |

HA did not expose an authoritative content ID with advancing position in the cold runs. Physically confirmed playback can therefore return uncertain and require operator reconciliation. Assist ended before Core returned its result in both cold runs, so there was no final spoken status. An earlier Infuse run reached a resume prompt. Installed Infuse version and Now Playing API availability remain unverified. These are accepted operating limits for BOF-86. Use the reconciliation procedure if playback state is unclear.

Run targeted parser and Assist contract tests under the existing offline harness and the full Python 3.13 CI regression, isolation and controller suites before deployment. The Assist contract tests exercise the HA agent, pinned Router renderer and Core with mocked services. They establish routing and safety behaviour without physical commands. Production acceptance checks release identity, service health and existing contracts through the established non-actuating pipeline. See [ADR 012](adr/012-bounded-video-through-jellyfin-and-ha.md) for the design decision.

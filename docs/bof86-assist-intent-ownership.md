# BOF-86 Assist intent ownership correction

## Change and boundary

The Jarvis conversation entity advertises `ConversationEntityFeature.CONTROL`.
In the inspected Home Assistant **2026.10.4**, this excludes
`HassMediaSearchAndPlay` and `HassGetState` from Assist's local-first pass.
The integration delegates **only HassGetState** back to the native strict
intent handler, preserving its response, user context and canonical chat ID.
Native media search is never delegated back. Existing local-first lights,
switches, pause and volume controls retain their pipeline path. Existing custom
sentence triggers still precede agent selection; no pipeline assignments,
preferred pipeline, entity aliases or exposure settings change.

This is an agent capability declaration, not a new HA tool/API permission.
Core video recognition removes only a leading `Can you` / `Could you` before
`play`. Existing catalogue-derived bare-title ownership, explicit music
exclusions, punctuation, year and destination handling remain in place.
Unknown `Moa` is not expanded into `Moana`; known ambiguous catalogue titles
still require resolution. `VIDEO_ENABLED=false` remains unchanged.

## Offline evidence and limits

The regression suite executes pinned excerpts of the installed HA local-first
filter/dispatch and strict intent handler, the actual repository integration
method, the accepted Router response renderer, and real Core ASGI authentication,
request schema and capability dispatch. It reproduces the pre-CONTROL native
media failure and verifies the corrected ownership through disabled Core.

Sentence recognition, exposed entities, native services, network hops and music
classification/execution dependencies are isolated mocks. This is not a full HA
framework run, a live Music Assistant playback test or spoken EchoMuse acceptance.
The Stereophonics regression verifies delivery to the existing music capability
and explicit-play boundary with the originating Office area; it does not claim
actual speaker playback. Existing nutrition/general conversation and ambiguous
catalogue contracts run alongside these tests. No live requests are replayed
during development because native interception can actuate devices even when
Core video is disabled.

## Separate authorised rollout

1. Review the MR and exact-HEAD CI. Merge only after approval. Obtain separate
   production rollout authorisation; this change does not authorise deployment.
2. Using the existing protected-main workflow in `cd.md`, qualify a fresh immutable
   package, run the existing production preflight, preserve configuration/state,
   verify retained rollback release/backups and deploy Core with effective
   `VIDEO_ENABLED=false`. Record package, receipt and acceptance evidence. The HA
   integration remains excluded from Core packaging.
3. Before installing the HA change, confirm its current API still has the inspected
   CONTROL filter and `conversation.async_handle_intents(..., intent_filter=...)`
   contract. Back up `/config/custom_components/jarvis_router/conversation.py`
   using the established timestamped backup procedure, recording its hash and
   exact rollback path. Install only the reviewed `conversation.py`, verify its
   SHA-256, then perform the separately approved HA Core restart. Do not change
   pipelines, aliases, credentials or other integration files.
4. Confirm HA health, `conversation.jarvis_router` availability and advertised
   `supported_features & 1`. Keep local preference enabled on the existing Jarvis
   pipelines and video disabled. Verify native state queries and conversation-ID
   continuity. Test real native actuator controls only with explicit test approval
   for the target; use mocks during development.
5. Under a separately authorised integration acceptance window, test the listed
   film phrases through the actual Assist pipeline, recording processed_locally,
   request correlation and terminal Core video/disabled response. Prove zero HA
   media-service calls and no Jellyfin access in disabled mode. Verify music,
   nutrition, general routing and native state questions. A successful offline
   contract is not a substitute for these runtime checks. Speaker playback needs
   its own bounded approval; no TV playback is required for this rollout.
6. Stop on any regression. Restore the exact backed-up HA file and use the
   established approved HA restart procedure, then recheck health. Roll back Core
   separately through the documented retained-release procedure if needed, keeping
   video disabled. Do not compensate with media commands or retry uncertain ones.

The global Home Assistant Local preferred pipeline is intentionally unchanged;
only pipelines selecting Jarvis gain the corrected ownership. Broader security,
runner and infrastructure work remains PARKED.

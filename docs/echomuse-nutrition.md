# EchoMuse nutrition routing repair

## Read-only diagnosis, 20 October 2026

Production Core RELEASE.json identifies c8e57ab0da0f3519607e46e895392b4130ae079f. The deployed Router source is its managed bf1732f release. No source/configuration was changed during diagnosis.

Physical HA Assist traces selected pipeline 01m293n1xh012c0hh0tjbxc68f, conversation.jarvis_router, Faster Whisper STT and Piper en_GB TTS. The global preferred pipeline is Home Assistant Local, so the default pipeline must not be assumed to represent the physical device. The physical runs identify the existing Office Assist satellite; no device firmware or pipeline selection was changed.

| UTC / trace | Observed boundary evidence |
|---|---|
| 19:15:23 / 01M5DBTKPJWDFRWYEXA3KYNNBZ | Calorie total transcription correct; Router logged handled=True, domain=nutrition; HA speech and TTS input were exactly Done. |
| 19:15:34 / 01M5DBTXHJ09XCXQQZ0ZNW4REA | Protein query followed the same path and lost its result at Router. |
| 19:15:44 / 01M5DBV8SG8KKHN8SDQ6C2ZDHZ | Remaining calories followed the same path and lost its result at Router. |
| 19:15:54 / 01M5DBVHY16P715983H5HZ3ZE7 | Yesterday's diary followed the same path and lost its result at Router. |
| 19:16:04 / 01M5DBVTXGH9TZ78W632J9DDQS | Daily target not matched by Core; handled=False, semantic fallback; general agent asked for body measurements. |
| 19:02:31 / 01M5DB2YGHDAA6HZSV1BPE5M02 | 750ml water transcription correct; Core declined, general fallback denied diary access. |

Direct read-only Core reproductions returned native structured read results for the first four phrases, without speech. Router's handled branch read music name/target_name fields for every domain and otherwise manufactured Done. HA forwarded that exact speech, rather than replacing a native answer. Prefix stripping and case-insensitive matching already accepted leading transcription whitespace, case and punctuation for these queries; these were not the cause.

HA traces retain one conversation ID over the repeated questions, but the deployed integration forwarded only text/area/satellite; Router likewise omitted conversation ID. Core keyed drafts by device/listener and required nutrition: for follow-ups. HA always set continue_conversation=False. Target and water were outside the initial intent matcher. Native tools/list confirms sparky_manage_food log_water(amount_ml, entry_date), independent of food entries; Jarvis's prior write allowlist excluded it.

## Bounded repair and contract

Core /request accepts optional conversation_id, origin, user_context and request_id in addition to the established payload. Existing callers remain compatible. Authenticated callers supply identity context; this is a trusted single-account service boundary, not delegated multi-user authorization. Do not expose the service as an unauthenticated chatbot API.

Nutrition responses retain structured result and add speech, operation_status, conversation_id, request_id and continue_conversation. Text is generated deterministically from native results, never from a model. Read totals use native data/goal and explicit units; incomplete data is qualified. Clarification/confirmation stays open; errors do not claim success. Unknown/missing results fail closed. Router forwards this contract only for nutrition and preserves music and L/D/C behavior. Nutrition transport failure cannot fall through to an untooled general LLM.

HA forwarding source is tracked under integrations/homeassistant/jarvis_router/conversation.py. It preserves user/session/request context, emits HA query_answer for reads and error for failed/uncertain operations, and honors continuation. It does not change pipeline selection or STT/TTS settings. Deploy the Core and Router exact-commit releases through their existing GitLab manual gates first. Then deploy this reviewed integration source to the existing custom component, retaining its original file locally on HA. Installed HA config-entry reload reuses cached component/platform Python modules and cannot activate changed source. Obtain explicit approval for a brief Home Assistant Core restart to load it; do not reboot the VM/Proxmox host or edit .storage. Rollback restores the retained component file and requires another approved HA Core restart; Core/Router rollback uses their existing release procedures.

Unprefixed bounded replies use the same unexpired session and device/user context: lunch, today, 08:15, 30 grams, product NAME, choice two, variant one, or an ordinary product name when explicitly requested. nutrition: remains a compatibility/diagnostic input. Unrelated HA controls, music and general questions are not claimed by a pending draft. No food, pack weight, nutrition or ambiguous date/time is invented. Writes and destructive changes require confirmation; durable existing receipts suppress duplicate confirmations and block uncertain retries.

Water accepts one positive numeric amount in ml/millilitres or l/litres, up to 10 litres, for today (default disclosed in confirmation) or yesterday. It writes only native log_water after confirmation, not a fabricated food. Native MCP hydration is date-granular; it does not accept a historical consumption clock. Receipt reservation precedes the call; ambiguous outcomes are never retried automatically. Native log_water acknowledgment omits an entry ID, so independent acceptance must compare itemized water logs and totals and remove only the identified fixture via the supported native API.

## Acceptance and privacy

Automated offline tests, deployed Core/Router/HA requests and physical microphone runs are separate evidence classes. Do not mark Task 5 complete before user-confirmed physical responses reconcile with HA pipeline traces and Router/Core metadata. Existing Task 4 backend acceptance remains baseline evidence, not physical voice acceptance.

Logs: CT120 journalctl -u jarvis-router records request ID/domain/status; CT122 journalctl -u jarvis-core records nutrition request ID/status. HA Assist pipeline_debug/list and pipeline_debug/get provide run IDs, STT/intent/TTS boundaries. Do not persist raw personal diary results, health totals, audio access tokens or credentials in Git/CI. Raw health-bearing acceptance state belongs only in root-restricted LXC files; workstation files contain scripts and redacted evidence only.

## Deployed automated acceptance

Core main `2a0a2b261b543b00511147accb647964b7d6fcd7` passed pipeline #102: all 186 regression tests, validation, packaging, user-started deployment #342 and production acceptance #343. Router main `e2971f750c2a2a4e41b2dba8d1fbd63c0cf9e125` passed web pipeline #103: 34 application tests, 86 deployment tests, packaging, user-started deployment #348 and acceptance #349. No direct SSH application deployment bypassed either gate.

After both gates passed, the explicitly approved HA forwarding patch was installed atomically, with its original file retained as `/config/custom_components/jarvis_router/conversation.py.pre-task5-20261020`. Original SHA-256: `683a3f13cc665fc9495c03058e62d0702438af820c207688f5fbebfaff525718`; installed SHA-256: `28573d759a90dda766f4a04aaaef4617f7752c55c482b4e991f2491bbe9095fb`. One approved Home Assistant Core restart loaded it. HA authenticated API recovered; the integration is loaded and has no matching system-log error. No VM/Proxmox reboot occurred. Restoring the retained file and restarting HA Core is the exact rollback; another disruptive restart requires approval.

Live tests separately exercised direct Core, Router port 8099 and HA's conversation-agent API. All five reported reads returned useful deterministic speech; HA query_answer retained the exact Core answer. Native calories/macros and effective-goal remaining arithmetic matched; dates used Europe/London. Private absolute values were not printed or committed. An actual HA session clarified an ambiguous saved food, accepted unprefixed choice/date/time replies, and confirmed two fixture slices (+160 kcal). Exact-entry correction to three total slices gave +240 kcal; repeat confirmation was suppressed. The HA-to-native hydration path created exactly one separate 750 ml record. All test foods/entries/water were removed; the original daily food summary and water record IDs were restored exactly.

Router/Core logs correlate native read and write operations using request IDs and actual adapter call counts. Example synthetic acceptance identifiers: calorie read `f4ff1fa029214d79b595e60ab399f352` (two MCP calls); confirmed hydration `839d9d310e834fe9b6cc7d654402a47c` (one MCP call). Clarification and unconfirmed water preparation can legitimately have zero MCP calls. Metadata contains no nutrient values or credentials.

A live synthetic general-knowledge request passed the unchanged Router fallback and answered Paris. Existing HA control/music/general behavior has offline regression coverage; physical actuation and audible music are not claimed from mocks. Core health was healthy; Observer remained running/live with successful cycles and no last error after HA recovered. All existing nutrition containers remained healthy; Mealie retained its uptime. No new service/container, dependency or inference server was introduced.

**Physical EchoMuse acceptance remains pending.** HA API calls are not microphone tests. The user has been asked to repeat the six reported phrases and a dinner-to-lunch clarification without nutrition:. Reconcile actual audible results with the physical Office EchoMuse pipeline traces and Router/Core metadata before declaring Task 5 complete. Leave the physical water request unconfirmed unless real consumption is intended; preparation alone does not write hydration data.

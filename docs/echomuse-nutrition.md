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

Physical EchoMuse acceptance subsequently passed, including the final shorter-wording readbacks below. HA API evidence remains distinct from the actual microphone results. Water preparation alone does not write hydration data; the physical user explicitly confirmed the retained entry.

## Physical routing acceptance and spoken-date correction

The user performed the actual Office EchoMuse microphone tests and reported results. HA traces confirm Faster Whisper transcription, conversation.jarvis_router dispatch, and identical intent speech/Piper TTS input. All runs retained conversation ID 01M5DFNP7KAJYQ50F3HE4P9W7A. No personal totals are recorded here.

| Run start, Europe/London | HA run ID | Result / native MCP calls |
|---|---|---|
| 21:22:31 | 01M5DFNP7KNHJACPEAPWXQZ35V | Calorie read; 2 calls; transcription omitted today and still matched |
| 21:23:06 | 01M5DFPR74MJKE2YY9GR59GDCZ | Protein read; 2 calls |
| 21:23:57 | 01M5DFRAH5X74YZ5A732WDXDAF | Remaining allowance; 2 calls |
| 21:25:29 | 01M5DFV3NM1N98MVYM6YM208GQ | Accurate empty yesterday diary; 1 call |
| 21:26:06 | 01M5DFW8A4GKQHTHJ787N5FN09 | Configured target; 1 call; no measurements requested |
| 21:26:42 | 01M5DFXBCPCTMN4N5AYKESGYCJ | Separate 750 ml water confirmation; 0 calls, no write |
| 21:26:56 | 01M5DFXSAV20WEVS5WS7K6FYY6 | Physical Yes; completed; 1 call; one corresponding native water record independently verified and retained |
| 21:28:06 | 01M5DFZX15A8FV8TBZGR17KE6P | Dinner ambiguity clarified; 0 calls |
| 21:28:13 | 01M5DG04C4H5Z9NBE046MKMD2K | Unprefixed lunch continued asking for food; 0 calls |
| 21:28:21 | 01M5DG0BXMABP7VJ3FASPD0JKX | Unprefixed Cancel acknowledged no diary changes; 0 calls |

Correlated Router request IDs include calorie 43820fae305640bca864a96417369bdb, protein 162443b6803549ce8788b85b622f7173, remaining 427e1456c6474820885368df89350fa3, water preparation 01106274ab9e4b57a9ebfca486b7ac14, confirmed water 8784839e8e294d9d84fee6c1422db872 and cancellation 256d25d56fbb4da4b5920e74a05cc842. Confirmed user consumption is not deleted as an automated fixture.

Routing, native reads, physical confirmation and unprefixed continuation/cancellation passed. The user found the ending difficult to understand and heard dash. The trace establishes the cause: Core appended ISO dates, and HA sent those same strings to TTS. The user requested removing repetitive spoken dates and explicitly excluded EchoMuse audio-setting troubleshooting.

The focused Core correction keeps structured dates, native calculations, confirmation and receipts unchanged. Current-day totals use today, the target omits the ISO suffix, remaining allowance simply states calories left, and water confirmation/acknowledgement omits routine date suffixes. Historical totals retain yesterday or a human-readable date, avoiding ISO punctuation without silently substituting today. No Router/HA code, firmware or audio setting changes are needed. Deploy through the existing Core gate and verify two short physical readbacks before closing the remaining speech correction.

## Final acceptance: COMPLETE

The shorter wording is deployed as Core `979b94ac42ddc08ab1607bd7789b955db50e1b22`. Pipeline #107 passed validation, all 193 regressions, packaging, user-started deployment #362 and production acceptance #363. Live Core/Router/HA tests confirmed the short current-day responses, retained historical context and unchanged structured dates. A temporary water confirmation was cancelled without a write; all native water record IDs, including the user's physically confirmed entry, were preserved. Router remains on `e2971f750c2a2a4e41b2dba8d1fbd63c0cf9e125`; no second HA restart or audio-setting change occurred.

The user reported that the final actual EchoMuse replies were spot on. HA runs at 21:50:25 and 21:50:38 Europe/London verify the physical Office satellite, correct transcription, HA query_answer, and identical useful speech/Piper input with no ISO suffix. Run IDs: calorie `01M5DH8S0NT1EH888BDPCDZ4VZ`, remaining allowance `01M5DH95K3ZTVQEK8V5TR4V7GM`. Router request IDs `8b10511eda82439c90305b0e85063b18` and `2efafbecfa8145e28e3f7a1ccec0685f` each show handled=True, domain=nutrition, status=read and two native MCP calls. Private numeric totals are omitted.

Task 5 operational routing and final physical speech acceptance are complete. Existing HA-control/music behavior retains regression coverage; no claim is made that mocked control/music tests are physical actuation tests. General LLM routing and Observer health were verified live. No new infrastructure or application upgrade was introduced. Preserve the documented rollback copy and receipt state, and include changed source/configuration/state in the existing backup process. This final update is documentation only and does not require redeploying Core.

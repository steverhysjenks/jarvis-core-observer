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

Production acceptance and physical results are pending at this preparation checkpoint.

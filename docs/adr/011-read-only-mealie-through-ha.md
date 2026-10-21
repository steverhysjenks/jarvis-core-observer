# ADR 011: Read-only Mealie lookup through Home Assistant

Status: Accepted for implementation; production enablement is separate.

## Context

Core already uses HomeAssistantClient.call_service with response support. Nutrition independently verifies source macros through a dedicated Mealie token; recipe browsing must not alter that write-provenance boundary. On 21 October 2026 read-only inspection of the connected HA instance confirmed its loaded Mealie integration and get_recipes/get_recipe contracts. Search with result_limit=1 returned service_response.recipes.items with recipe_id, name and slug. A detail read by returned recipe_id yielded service_response.recipe with ingredients[].display, recipe_servings and instructions[].text. A no-match search yielded items=[]. No live configuration or records were changed.

## Decision

Reuse HA rather than add another authenticated Mealie HTTP client. Restrict the new adapter to two named read services, with configured integration ID and return_response=True. Search at most six candidates; fetch details only for a unique match. The deployed HA wrapper exposes no total/page metadata, so full pages are potentially truncated and never auto-selected. Recognition is deterministic. Register after nutrition and before music so existing replay and nutrition priority remains intact, while explicit recipes avoid music's semantic classifier. Disabled and failed recognised requests stay claimed to prevent inferred recipe answers.

Keep ingredient display strings from the authoritative record without reconstruction, unit conversion or serving estimates. Treat missing source data as incomplete/unavailable. Return concise speech and structured recipe data, including recorded instructions without cooking state. No new credentials, generic service execution, retries, caching, LLM calls or mutation paths.

## Consequences

Availability depends on HA and Mealie. Existing HA token permissions exceed these two operations; the restriction is enforced in Core, not a claim of HA per-service scopes. Reuse avoids copying or rotating live credentials. The separate nutrition provenance integration is not refactored in this increment. Ambiguity asks users to repeat a fuller name; no dialogue state is persisted. Rollback is the default-off feature flag.

## References

- https://github.com/home-assistant/core/blob/dev/homeassistant/components/mealie/services.yaml
- https://github.com/home-assistant/core/blob/dev/homeassistant/components/mealie/services.py
- Connected HA read-service contract and sample responses verified 21 October 2026; tests use synthetic fixtures only.

## Amendment — single recipe request deadline (21 October 2026)

Keep the two read-only HA services and add a single fixed 15-second monotonic deadline at Mealie capability entry. Pass its absolute time to both adapter reads and enclose lookup/detail/response preparation in asyncio.timeout_at; check expiry before each read and before returning a prepared result. This replaces independent potential 30-second HA waits with one shared cancellation boundary. No Router timeout or unrelated HA consumer changes are needed.

Timeout remains owned by Mealie: return unavailable with reason=deadline_exceeded, not semantic fallback, partial data or retry. External task cancellation propagates. Awaited client work unwinds normally; an already-sent remote read cannot be recalled. No task is shielded or abandoned. The five-second nominal Router margin is for earlier dispatch, cleanup, ASGI serialization and transport; cooperative cancellation cannot guarantee real-time scheduling or successful delivery during network/event-loop failure.

Offline tests cover slow search/detail cancellation, shared absolute deadlines, already-exhausted budgets, rejection after response preparation, normal authoritative ingredients and caller cancellation. Controlled latency/client acceptance remains a deployment gate. This amendment is proposed for review on the deadline branch; it does not authorise a merge, deployment, restart or feature enablement.

Reference: https://docs.python.org/3.13/library/asyncio-task.html#asyncio.timeout_at

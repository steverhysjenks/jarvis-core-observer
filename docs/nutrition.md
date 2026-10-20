# Nutrition capability and recovery

The optional `NUTRITION_ENABLED=true` capability uses SparkyFitness v1.8.0's native MCP endpoint, not the retired standalone server. It is disabled by default. Read and mutation requests use distinct account-scoped API keys stored in root-managed, jarvis-readable files. The full key is technically broader than diary writes; the adapter restricts it to log/update/delete-entry actions. Do not expose generic MCP execution, goals or AI tools.

`POST /request` retains its existing authentication and adds optional `request_id`, `nutrition` and `nutrition_confirmation`. A resolved `nutrition` selection contains an existing food/variant UUID, quantity/unit, explicit timezone-aware consumption timestamp and unambiguous meal. Pack fractions also require an explicit pack weight. The response supplies a confirmation ID. Repeat the same request ID on retries. Confirm using `nutrition_confirmation` from the same listener/area/satellite context. Writes never use an LLM to invent a product, serving or nutrient.

Ambiguous natural-language examples return clarification without writing. Core accepts structured selections and bounded nutrition: follow-ups with numbered product/entry choices. It asks for actual remaining grams rather than inferring which packet “the rest” refers to. Dinner requires lunch/evening clarification. Corrections/removals require an exact dated diary UUID and confirmation. Reads support saved-food search, today's native totals/effective remaining calories and today/yesterday history. History retains native pagination metadata; the first 50 entries are not represented as a complete large diary.

OFF/Mealie writes require source-declared core nutrients. Unknown native micronutrients are conservatively returned as null, including values whose completeness cannot be established. The native app still displays zero for missing nutrients, as accepted by the user. No health data is sent to an inference provider. Mealie remains authoritative for recipes; this client does not modify recipes.

## Runtime files

- `/etc/jarvis-core/secrets/sparky-read.token` and `sparky-write.token`: dedicated API keys; 90-day expiry, renew before expiry through Sparky's supported API-key UI.
- `/etc/jarvis-core/secrets/mealie-recipes.token`: dedicated recipe token, distinct from Home Assistant's.
- Directory root:jarvis 0750, files root:jarvis 0640; paths only in `/etc/jarvis-core/jarvis.env`. Never put values in Git, CI variables, traces or artifacts.
- `/var/lib/jarvis-core/nutrition-receipts.sqlite`: private write receipts and pending payloads. Include in CT122 PBS backup. Pending confirmations expire after ten minutes; completed/uncertain receipts remain to prevent duplicate retries. Contains personal diary references; restrict access with the existing service state-directory permissions.

A SQLite transaction commits `in_flight` before sending a write. A timeout or unrecognised acknowledgement leaves reconciliation required; inspect the native diary and reconcile the receipt before issuing another write. New writes from that context are blocked while any receipt remains uncertain/in_flight. Do not clear receipts to retry an uncertain action. This intentionally favours avoiding duplicate entries over automatic recovery.

## Deployment and rollback

Use the existing protected-main GitLab validation, isolated regression, package, manual `deploy_production` and production acceptance workflow. No SSH application deployment. Configure credential paths before enabling. Validate real temporary labelled food entry, totals, correction and deletion through deployed Core; offline tests alone do not establish acceptance.

Disable `NUTRITION_ENABLED` and restart Core to withdraw only this capability, or use the existing release rollback. Preserve receipts and credentials across rollback. Existing HA, Music Assistant, observer and LOCAL/DESKTOP/CLOUD routing remain in place. Do not enable SparkyAI/cloud ingestion as part of this deployment.

## Bounded voice clarification

Core now resolves explicit follow-up details without changing Router or sending health data to a model. Start with a supported food request, then prefix follow-ups with `nutrition:` so a pending food dialogue cannot steal unrelated music commands. For example:

1. `I had half a packet of biscuits.`
2. `nutrition: product Exact saved biscuit name; snack; today at 12:30; packet weighs 300 g`
3. Confirm the exact food, computed grams, meal and timestamp using the returned confirmation ID or `yes` when exactly one action is pending.

Saved-food and diary ambiguity returns numbered choices. Reply `nutrition: choice 2` for foods, `nutrition: entry 2` for dated diary entries, or `nutrition: variant 2; 1 serving` for an explicitly defined serving reference. A correction such as changing toast to three slices treats three as the corrected total. Exact dated entries and explicit confirmation remain required. `nutrition cancel` cancels pending actions without touching the diary.

Replies are deliberately bounded: explicit product names, positive amounts with supported units, unambiguous meals, today/yesterday/ISO dates, and 24-hour HH:MM consumption times. `just now` is an explicit consumption-time instruction. “Dinner” still requires lunch/evening clarification; “half past twelve” asks for an unambiguous clock time. “The rest” requires actual remaining grams and product identity, rather than guessing a packet association. Missing slice weights are not inferred. Numbered choices are valid only within the same trusted listener/area/satellite context for ten minutes.

An explicit native variant can now accept serving counts even when its reference unit is grams; Sparky performs the calculation. DST-ambiguous/skipped local times require the existing offset-aware structured request, rather than guessing an offset. The dialogue stores private ten-minute drafts in the same mode-0600 receipt database; include it in CT122 backup coverage. Structured inputs remain supported for callers that already resolved the selection.


History also accepts explicit ISO date ranges of at most 31 days and numbered pages (`What did I eat 2026-10-01 to 2026-10-20 evening page 2?`). Each page has at most 50 native entries and retains has_more/next_offset; iterate pages and bounded ranges for later pattern analysis. Structured callers may send `nutrition_history: {start_date, end_date, offset}`. Unsupported relative dates are clarified instead of silently returning today. Explicit single-date/yesterday totals use the matching native effective goal. Evening filtering applies to food and meal entries; missing times remain unclassified.

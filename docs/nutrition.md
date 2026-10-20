# Nutrition capability and recovery

The optional `NUTRITION_ENABLED=true` capability uses SparkyFitness v1.8.0's native MCP endpoint, not the retired standalone server. It is disabled by default. Read and mutation requests use distinct account-scoped API keys stored in root-managed, jarvis-readable files. The full key is technically broader than diary writes; the adapter restricts it to log/update/delete-entry actions. Do not expose generic MCP execution, goals or AI tools.

`POST /request` retains its existing authentication and adds optional `request_id`, `nutrition` and `nutrition_confirmation`. A resolved `nutrition` selection contains an existing food/variant UUID, quantity/unit, explicit timezone-aware consumption timestamp and unambiguous meal. Pack fractions also require an explicit pack weight. The response supplies a confirmation ID. Repeat the same request ID on retries. Confirm using `nutrition_confirmation` from the same listener/area/satellite context. Writes never use an LLM to invent a product, serving or nutrient.

Ambiguous natural-language examples return clarification without writing. This first implementation provides structured resolution for the caller; it does not yet implement a complete conversational product-selection UI or resolve “the rest of that packet” automatically. Dinner requires lunch/evening clarification. Corrections/removals require an exact dated diary UUID and confirmation. Reads support saved-food search, today's native totals/effective remaining calories and today/yesterday history. History retains native pagination metadata; the first 50 entries are not represented as a complete large diary.

OFF/Mealie writes require source-declared core nutrients. Unknown native micronutrients are conservatively returned as null, including values whose completeness cannot be established. The native app still displays zero for missing nutrients, as accepted by the user. No health data is sent to an inference provider. Mealie remains authoritative for recipes; this client does not modify recipes.

## Runtime files

- `/etc/jarvis-core/secrets/sparky-read.token` and `sparky-write.token`: dedicated API keys; 90-day expiry, renew before expiry through Sparky's supported API-key UI.
- `/etc/jarvis-core/secrets/mealie-recipes.token`: dedicated recipe token, distinct from Home Assistant's.
- Directory root:jarvis 0750, files root:jarvis 0640; paths only in `/etc/jarvis-core/jarvis.env`. Never put values in Git, CI variables, traces or artifacts.
- `/var/lib/jarvis-core/nutrition-receipts.sqlite`: private write receipts and pending payloads. Include in CT122 PBS backup. Pending confirmations expire after ten minutes; completed/uncertain receipts remain to prevent duplicate retries. Contains personal diary references; restrict access with the existing service state-directory permissions.

A SQLite transaction commits `in_flight` before sending a write. A timeout or unrecognised acknowledgement leaves reconciliation required; inspect the native diary before issuing a new request ID. Do not clear receipts to retry an uncertain action. This intentionally favours avoiding duplicate entries over automatic recovery.

## Deployment and rollback

Use the existing protected-main GitLab validation, isolated regression, package, manual `deploy_production` and production acceptance workflow. No SSH application deployment. Configure credential paths before enabling. Validate real temporary labelled food entry, totals, correction and deletion through deployed Core; offline tests alone do not establish acceptance.

Disable `NUTRITION_ENABLED` and restart Core to withdraw only this capability, or use the existing release rollback. Preserve receipts and credentials across rollback. Existing HA, Music Assistant, observer and LOCAL/DESKTOP/CLOUD routing remain in place. Do not enable SparkyAI/cloud ingestion as part of this deployment.

# ADR proposal: bounded nutrition MCP adapter

Status: proposed for operational acceptance, 20 October 2026.

Use the deployed SparkyFitness native MCP endpoint inside Core's existing bounded-capability dispatcher. Separate read-only and full account API keys, a fixed read/action allowlist, explicit source checks, structured portion/time resolution and confirmed mutations constrain the integration. No additional process, container, generic MCP platform or inference route is introduced.

Keep Sparky authoritative for diary arithmetic and effective goals. Keep Mealie authoritative for recipes. Unsupported nutrient completeness is unknown; never infer packet mass or macro values. Current native Mealie imports omit ingredient lists and full recipe yields; retrieve these from Mealie when needed.

The Core API remains the trusted authenticated caller boundary for a single configured Sparky account. Listener/context strings bind pending confirmations but are not independently authenticated household identities. Do not expose this capability to untrusted callers or treat those labels as account delegation. Multi-user identity mapping requires a separate design before broader rollout.

Durable private SQLite receipts reserve each write before transmission and retain uncertain outcomes for reconciliation. Completed receipts suppress retry duplication; a genuinely new identical consumption needs a distinct request ID. No automatic retry follows an uncertain write. Native micro-nutrient zeros are not sufficient provenance.

Feature flag defaults off. Existing protected-main manual deployment and production acceptance remain required. A real temporary diary write, correction, totals comparison and cleanup through deployed Core remain acceptance gates. A bounded Core dialogue now populates the strict schema from explicit nutrition: follow-ups and numbered native choices. It does not invent values or bypass confirmation; unrelated music requests are not intercepted by pending food dialogue.


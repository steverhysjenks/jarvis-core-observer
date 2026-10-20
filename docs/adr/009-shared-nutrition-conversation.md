# ADR proposal: shared nutrition conversation response

Status: proposed, 20 October 2026.

Production EchoMuse evidence showed successful native Core results being replaced by Router's music-specific Done fallback. Session IDs also stopped at HA. Repair these boundaries rather than changing model classification or duplicating the nutrition backend.

Use the existing authenticated Core /request as the shared capability interface for voice and future text clients. Carry optional session, origin, authenticated caller-supplied user context and request correlation. Preserve legacy requests and structured results. Add deterministic speech/status/continuation for nutrition, with native values and no model inference. Router and HA pass it through, and bounded clarification uses expiring session state. Uncertain writes retain at-most-once receipts across releases. Hydration uses native Sparky water records, not another database.

No generic MCP platform, chatbot, inference service or new infrastructure is introduced. Preserve HA, Music Assistant, observer and existing L/D/C classification. The existing trusted single-account authentication boundary remains; broader account delegation requires a separate review. See docs/echomuse-nutrition.md for diagnosis, rollout, rollback and acceptance gates.

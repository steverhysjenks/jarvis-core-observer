# ADR proposal: bounded read-only HA nutrition projection

Status: proposed, 21 October 2026.

Expose two authenticated GET routes in existing Jarvis Core, using its existing read-scoped native Sparky MCP adapter. A dedicated file-backed HA token authorizes only these summaries. The existing broad conversational credential and write token are not given to HA. No new process, database, MCP server or scheduler is introduced.

Native date-range aggregates supply the full 14-day window in one call. Missing dates remain null. Average only usable completed logged days, excluding today's partial intake; expose today and counts separately. Preserve native effective-goal semantics and document v1.8.0's loss of missing-nutrient provenance.

Native RESTful HA resources share one payload per polling group (180/7200 seconds). Exclude all nutrition entities from Recorder, with bounded history attributes used directly by a future dashboard. HA owns display only; Sparky retains all historical records and writes. Root-restricted local rollback copies, config validation and approved restart protect existing HA configuration. No dashboard changes are authorized here.

See `docs/nutrition-summary.md` for contracts, failure semantics and recovery. Operational acceptance remains required.

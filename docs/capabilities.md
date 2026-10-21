# Request capabilities

Jarvis Core does not send every request to a general-purpose LLM.

`POST /request` creates a `VoiceRequest`, then `voice/orchestrator.py` offers it to the bounded capability dispatcher.

## Dispatcher contract

Capabilities return a result that distinguishes whether the domain was **claimed** from whether the requested action was **handled**.

That difference is deliberate. If a request is clearly a music request but cannot safely be executed, music still owns the response. It must not fall through to a general semantic route which might reinterpret it and bypass the bounded policy.

## Replay capability

Replay recognises requests such as repeating the last announcement and calls the deterministic replay path. It does not ask an LLM to reconstruct what was said.

## Music capability

Music owns supported playback/control and semantic music requests. Explicit intent, semantic classification, grounded retrieval and playback remain separated so a semantic phrase cannot manufacture a catalogue URI.

## Wider semantic path

If no bounded capability claims the request, `voice/orchestrator.py` returns the request to the wider semantic path with canonical area/satellite/listener context.

That is the integration seam back toward the wider Jarvis routing architecture rather than an attempt to reproduce all V1 L/D/C routing inside Jarvis Core.

## Mealie recipes

The dispatcher order is replay, nutrition, Mealie, then music. Explicit `find my chicken curry recipe`, `show me my spaghetti bolognese recipe`, and `what ingredients do I need for lasagne?` requests use deterministic recognition and authoritative saved Mealie records. An optional `Jarvis,` prefix is accepted. No LLM calls, meal planning, recipe changes, shopping writes or cooking state are introduced.

Enable only at review/acceptance time with `MEALIE_ENABLED=true` and `MEALIE_HA_CONFIG_ENTRY_ID` identifying an already-loaded Mealie integration. The default is disabled; recognised requests return a disabled response instead of falling through to inference. Unrelated requests remain unclaimed. No additional Mealie credentials are needed: HA retains its existing integration token and Core uses its existing server-side HA configuration. The adapter exposes only get_recipes/get_recipe; HA authentication itself is broader than this application-level allowlist. Use an existing dedicated non-admin HA identity with only necessary access where supported; HA does not provide per-service token scopes. Never expose credentials to callers or logs.

Responses use domain `mealie`, path `ha_recipe_read`, `speech`, `operation_status`, `intent`, `query`, and source `mealie`. Statuses: found, not_found, ambiguous, disabled, incomplete, unavailable. A successful result contains the source recipe ID, slug, name, description, servings, ingredient display strings and instructions. No quantities are inferred or scaled. At most six ingredients are spoken, with explicit partial-list wording; full ingredient data remains structured. Exception details and raw upstream responses are not logged or returned.

Search requests at most six records, then fetches one detail record only when exactly one match exists. Multiple matches always require repeating the request with a full name; no implicit selection or numbered follow-up state is added. HA's deployed search wrapper omits totals, so a full page is marked possibly_truncated. Detail failure, malformed data, missing config and upstream errors remain claimed and fail closed. A recipe removed between search/detail is unavailable rather than fabricated. Empty or missing ingredient text is reported as incomplete. Recipe lookup returns recorded instructions as data; it does not start cooking guidance or claim a screen was opened.

Offline coverage: `tests/regression/test_mealie.py`, included in the reviewed isolation allowlist and existing GitLab regression job. Run `python -B ci/validate.py --ci`, `python -B ci/test_deployment.py --junitxml results/deployment-units.xml`, and `python -B ci/run_offline.py` with Python 3.13 and the pinned requirements. No live credentials or services are required. Rollback: leave/set MEALIE_ENABLED=false; deployment remains a separate approval step. Physical spoken acceptance and presentation by downstream Router/HA clients remain unverified until an authorised deployment.

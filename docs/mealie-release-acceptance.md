# Mealie deadline release and controlled acceptance

Prepared 21 October 2026. This procedure is for review; no merge, deployment, configuration change, restart or Mealie enablement has been approved or performed. Read-only HA recipe inspection was used to choose a real fixture. Do not run the acceptance code while reviewing it.

## Reviewed release state

- Core main: e8eadaafb11b773ebeb21411b9bb659611ceee15. Deadline MR !18, branch fix/mealie-request-deadline, implementation d411a00ddb2c27eb80d67d2772b799489035867e is open/draft and conflict-free. Its pipeline #121 passed: 253 regression tests, nine isolation checks and validation/deployment units. Subsequent documentation commits must also have passing CI before review approval.
- Router main: e2971f750c2a2a4e41b2dba8d1fbd63c0cf9e125. MR !2 remains open/draft, conflict-free, head 160834a3987d3cfd5b69b7e726bd10eb302d1398; pipeline #120 passed validation, 43 application tests and 86 Linux deployment tests.
- Core pipeline #118 is blocked at manual deploy_production #399. package_release #398 identity.json still names e8eadaaf and application archive SHA-256 7595efb91ba4f7c086ccee5668027663048f3552f6160562675f011591fdddc4; acceptance #400 has not run. This package DOES NOT contain the new deadline. It is consistent with current main today, but is not the intended complete Mealie release.
- No replacement protected-main deadline deployment job exists yet: this MR is unmerged. Do not invent its ID or deploy the feature-branch artifact. After approved merge, record the new main SHA/pipeline and its manual deploy_production job ID; verify the packaged identity against that SHA. #399 becomes stale when main advances and the controller should refuse it. Seven-day artifact expiry also requires a fresh validated pipeline.

Links: [Core MR !18](https://gitlab.boffjenkins.co.uk/homelab/jarvis-core-observer/-/merge_requests/18), [implementation CI #121](https://gitlab.boffjenkins.co.uk/homelab/jarvis-core-observer/-/pipelines/121), [Router MR !2](https://gitlab.boffjenkins.co.uk/homelab/jarvis-router/-/merge_requests/2), [Router CI #120](https://gitlab.boffjenkins.co.uk/homelab/jarvis-router/-/pipelines/120).

## Approval 1: review and merges only

Review/approve the fixed 15-second cooperative deadline, claimed unavailable result, five-second nominal transport margin and Router's generic fail-closed outage policy. A Core outage also makes general Router inference unavailable; do not silently add a bypass. Obtain explicit approval to merge Core !18 and Router !2. Keep them draft/unmerged until that approval. Merge permission is not production permission.

After approved merges, wait for each exact-main validation/test/package job to pass. Recheck latest main before each deployment; inspect any intervening commits. Record the two merge SHAs, new pipeline/job IDs, package identities and previous active release targets. Core and Router maintain their existing separate protected environments, SSH identities, strict host pins and resource groups. Never change CI variables, keys or host pins to bypass a failed check.

## Approval 2: Core deployment, feature disabled

Target: CT122, stable guest IP 192.168.0.62. Current owner is NAB9; rediscover placement before host-side administration. Use the existing Core GitLab CD process in docs/cd.md, not an SSH copy of application files.

1. Require approved exact release, current backup/recovery evidence and existing production gates. If a preflight is needed, obtain approval for the existing read-only protected-main JARVIS_OPERATION=preflight job. Do not bootstrap an already-managed installation.
2. Verify MEALIE_ENABLED=false. Absence also defaults false, but retain the current explicit disabled configuration where present. Any environment edit requires approval identifying CT122; preserve file permissions and other keys. /etc/jarvis-core/jarvis.env is external to release artifacts. A pipeline variable does not set runtime configuration. Do not print the complete file, source it in a shell, or expose credentials.
3. Approve the NEW deadline-containing pipeline's deploy_production job with JARVIS_OPERATION=deploy, only after deployment approval. Do not click #399 for this release. The existing controller prepares, checks and activates the exact commit, restarts the existing service and verifies identity/health/Observer. No Proxmox or HA service restart is part of this step.
4. Require its automatic production_acceptance to pass; retain results/deployment.json and results/production.xml. Verify healthy /health, exact receipt/release identity (version 0.7.0 alone is insufficient), jarvis:jarvis process identity, unchanged Observer mode, running=true, last_error=null, a completed post-restart cycle and subsequent counter progression. Do not start a second Observer.
5. With the existing authorised Core client, issue one explicit recipe lookup and confirm domain=mealie, status=disabled and useful speech. Do not interpret a Router/HA result as this direct-Core check until Router is updated. Run agreed existing read-only nutrition acceptance and rely on the established regression suite for mocked controls; audible music/replay/device actions need to be included explicitly in the acceptance approval.

A failed production_acceptance does not automatically roll back a healthy activated Core. Stop the release sequence and inspect the sanitized failure evidence.

## Approval 3: Router deployment and disabled-path acceptance

Target: CT120, guest IP 192.168.0.121, current owner HP. Use docs/deployment.md and the existing Router opt-in protected-main workflow. Its feature pipeline has no production job.

1. Confirm Router !2's approved main artifact and existing protected router-production access. For the approved main web pipeline use ROUTER_CD_ENABLED=true, ROUTER_MUTATIONS_ENABLED=true, ROUTER_OPERATION=deploy, with the established scoped variables unchanged. Manually approve production_deploy only after explicit deployment approval. Do not bootstrap or modify LiteLLM/Qwen/agents.
2. Require the exact-receipt production_acceptance to pass. Retain its deployment receipt/JUnit. Check Router liveness, active release identity and LiteLLM non-interference; recheck Core health/Observer. The deployment job's existing restart is authorised only by that deployment approval.
3. Keep Mealie false. Through Router, then HA, confirm the direct-Core disabled speech/status survives with no L/D/C inference. Check valid semantic fallback for an unrelated question and existing nutrition/music/replay presentation. Use mocks or an isolated client setup for timeout/502/503 tests; never stop HA/Core to simulate an outage without separate approval. HA must not turn a capability failure into inference fallback or claim success.
4. Confirm the outer HA/Assist client budget/error handling is compatible with the unchanged 20-second Router Core timeout. Accept explicitly that network/transport failures can still produce a bounded unavailable response.

Neither existing automatic production acceptance profile proves new recipe speech or physical satellite behaviour; those remain distinct gates.

## Approval 4: controlled enablement and real-recipe latency window

A successful live Mealie test through production /request is impossible while MEALIE_ENABLED=false. Do not temporarily enable it without approval or report a disabled response as a successful recipe timing. The prerequisite gates are the reviewed deadline, passing exact-release CI/CD and production acceptance, disabled-path/client checks, known fixture/config ID, latency thresholds and a reviewed rollback. After those pass, obtain a separate approval identifying CT122, the two environment keys, one restart, the bounded read-only recipe tests and immediate disable/restart rollback if they fail. Alternatively, separately approve an isolated acceptance instance; its timings must not be presented as production /request acceptance.

The existing loaded HA Mealie entry was re-enumerated read-only as 01M5CPM2DXD2MZ1MPT3XMFJJMS. Reconfirm it against the same HA_URL before the window. Preserve all existing credentials. Under the established deployment lock/operator procedure, back up the current environment privately on CT122, set only:

    MEALIE_ENABLED=true
    MEALIE_HA_CONFIG_ENTRY_ID=01M5CPM2DXD2MZ1MPT3XMFJJMS

Restart jarvis-core once under the lock and reverify its health/Observer/identity. No daemon-reload, HA restart or Proxmox change is needed for environment-value changes. If the window is not approved, leave the flag false and defer the remaining success tests.

### Verified existing fixture

On 21 October, read-only mealie.get_recipes with search_terms=Creamy uniquely selected:

- Name: Creamy Pepper Jack Chicken with Bacon
- recipe_id: b36ae63e-dfba-4d8a-a4de-1dee29f93521
- slug: creamy-pepper-jack-chicken-with-bacon
- Detail read confirmed 12 recorded ingredients.
- Utterance: What ingredients do I need for Creamy?

Revalidate the unique query and source records immediately before acceptance; the user's catalogue may change. Full-title and pepper jack searches returned multiple records during preparation. That is existing upstream search behaviour, not a deadline fault: do not bypass ambiguity or hardcode a match. If the fixture changes, select another uniquely verified existing record without creating/editing a recipe.

### Short direct-Core timing test

After the approved enablement/restart, make at most three sequential read-only /request calls on CT122 loopback, with separate request IDs. Stop at the first failure; do not automatically retry it. Load the existing environment through the established systemd EnvironmentFile mechanism in an approved transient diagnostic process (never source/print the env file). The snippet below is a reviewable test body, not a command executed by this change. Run it using the installed Python, without importing app.main or starting Uvicorn/Observer. If stored as a temporary script, restrict and retain/remove it through the approved host-side procedure.

```python
import json
import os
import time
import urllib.request
import uuid

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
timings = []
for sample in range(3):
    request_id = str(uuid.uuid4())
    payload = json.dumps({
        'text': 'What ingredients do I need for Creamy?',
        'request_id': request_id,
    }).encode()
    request = urllib.request.Request(
        'http://127.0.0.1:8000/request', data=payload, method='POST',
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + os.environ['JARVIS_CORE_API_KEY']},
    )
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=18) as response:
            result = json.load(response)
        elapsed = time.perf_counter() - started
        recipe = result.get('result', {}).get('recipe', {})
        passed = (result.get('domain') == 'mealie'
                  and result.get('handled') is True
                  and result.get('operation_status') == 'found'
                  and isinstance(result.get('speech'), str)
                  and bool(result['speech'].strip())
                  and recipe.get('recipe_id') == 'b36ae63e-dfba-4d8a-a4de-1dee29f93521'
                  and isinstance(recipe.get('ingredients'), list)
                  and len(recipe['ingredients']) == 12
                  and elapsed < 18)
    except Exception:
        # No raw error, body, speech, key or private source records in output.
        print(json.dumps({'sample': sample + 1, 'request_id': request_id, 'pass': False}))
        raise SystemExit(1)
    print(json.dumps({'sample': sample + 1, 'request_id': request_id,
                      'seconds': round(elapsed, 3), 'pass': passed}))
    if not passed:
        raise SystemExit(1)
    timings.append(elapsed)
print(json.dumps({'samples': len(timings), 'max_seconds': round(max(timings), 3)}))
```

Compare actual ingredient display strings/quantities against the fresh HA/Mealie record privately; count/ID checks alone do not establish ingredient correctness. Three samples are a smoke test, not a statistical p95 claim. Require every direct success below 18 seconds, leaving at least nominal transport margin, and no timeout. A deadline-exceeded unavailable response is a safety pass for timeout handling but a failure of this successful-fixture acceptance. Offline tests cover that failure path without a live outage. The urllib timeout is not a hard total wall-clock process deadline; the explicit elapsed check also applies.

Then issue the same utterance through Router, HA conversation API and the physical satellite, in that order, stopping on failure. Require the authoritative title/ingredients, same bounded speech/status through forwarding and no L/D/C path for any claimed status. Measure Router response and confirm it arrives within its client budget; record request IDs and elapsed/status only, not credentials, diary data or raw traces. For the 12-ingredient fixture, voice may explicitly read only the first six and direct the user to the full details; it must not claim that six are the complete list. Verify an actually missing query and a source-confirmed ambiguous query are terminal. Include a general semantic question and agreed existing capability smoke checks. Never deliberately break HA/Mealie or execute nutrition writes as part of these read-only recipe tests.

Keep the feature enabled beyond the test window only if the approval explicitly allows that and all gates pass. Otherwise disable again through the approved rollback procedure.

## Rollback

Record previous managed release targets before each deployment. Never erase receipts, pending confirmations, SQLite, credentials, guest data or backups.

- Feature-first rollback: under the authorised CT122 lock/procedure restore MEALIE_ENABLED=false, restart once and verify direct disabled response, health and Observer progression. Preserve the ID and unrelated keys. This retains the new deadline and generic Router safety boundary.
- Core activation failure: the existing CD controller automatically restores/verifies its recorded previous release; failure remains a failed deployment. Later acceptance/regression requires separately approved recovery following docs/cd.md, the same lock and a verified previous target. Do not invoke an obsolete deployment pipeline to evade current-main validation. Restoring code does not reverse data changes.
- Router activation failure: use its existing journalled automatic recovery; later rollback uses the protected-main opt-in ROUTER_OPERATION=rollback workflow, recorded expected_current/target and manual production_rollback approval, followed by acceptance. Inspect interrupted transaction state before recovery; do not automatically retry uncertain jobs.
- Returning to a pre-boundary Router or a Core without the Mealie capability can allow recipe utterances back into inference. Setting the Core flag false alone does not repair the old Router. Prefer disabling the feature while retaining the new boundary. Any rollback removing that boundary requires a separately approved maintenance/client restriction preventing recipe requests; do not advertise recipe support until repaired and accepted.

## Exact next approval point

Approve review/merge of Core MR !18 and Router MR !2 only, after checking their latest heads and passing pipelines. No production approval is implied. Replacement protected-main deployment job IDs can only be named after those merges and packaging succeed. Subsequent approvals identify first the new Core disabled deployment, then Router deployment, and finally the CT122 enablement/latency window. No Proxmox action or credential change is required by this release.

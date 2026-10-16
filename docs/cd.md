# Controlled GitLab CD: LXC 122

## Scope and safeguards

Target: Debian 13 / Python 3.13 on `192.168.0.62`, SSH identity `ansible` with passwordless sudo. Runtime remains `jarvis:jarvis` under the unchanged `jarvis-core` systemd unit. No Docker runtime or service accounts are added on the LXC. The CI runner continues to use its existing Docker executor.

Validation and offline regression jobs are unchanged in purpose. Historical `docs/production-baseline-hashes.json` records the original internal 0.7.0 source; differences are now informational rather than a prohibition on future approved code changes. Do not rewrite this evidence to make a new release appear to be the original baseline.

Protected-main push/web pipelines package application Python source, runtime requirements and deployment checkers directly from Git objects at `CI_COMMIT_SHA`. Tracked checkout changes and untracked source/test/deployment files are rejected. The package is created only after validation and regression succeed. Deployment independently compares artifact files/controller with that same commit, checks its digest/manifest/version, and rejects a manual pipeline if remote main has moved. No working-tree or branch-name archive is deployed. Artifact expiry is seven days; after expiry, use a new validated pipeline rather than rebuilding an unvalidated artifact.

Three manual operation choices share `resource_group: jarvis-core-lxc122` and an additional target-side flock for mutations. Only one production operation is offered per pipeline, selected with `JARVIS_OPERATION` (`deploy` by default; `preflight` or `bootstrap` in a manually created main pipeline). Deploy/bootstrap jobs are blocking, noninterruptible and require explicit clicks. Bootstrap additionally requires `JARVIS_BOOTSTRAP_APPROVAL=MIGRATE_REAL_DIRECTORY_LXC122`. Do not set that phrase as a permanent project variable.

## GitLab configuration prerequisites (not configured by this change)

1. Protect `main`: restrict push/merge rights, prohibit force pushes, require reviewed merge requests and successful validation/regression. Restrict changes to CI/deployment files through review/CODEOWNERS policy as appropriate.
2. Protect the `production` environment and explicitly restrict Allowed to deploy to the designated maintainers/operators. Configure deployment approval rules if available/required. A manual job is a deliberate operator gate; it is not automatically an independent second-person approval. Protected-environment/approval availability depends on GitLab tier. If unavailable, do not enable production credentials until equivalent operator access restrictions are established.
3. Register/confirm a protected runner tagged `docker`, trusted for protected-main jobs. It must reach the GitLab registry/package index and `192.168.0.62:22`. Do not mount host secrets, production storage or a Docker socket into jobs; avoid privileged mode. Enable prevention of outdated deployment jobs and configure the resource group processing policy if appropriate.
4. Use the shared GitLab group-level **protected, file-type** variables, both environment-scoped to **production**: `HOMELAB_SSH_PRIVATE_KEY` (the existing ansible deployment private key) and `HOMELAB_SSH_KNOWN_HOSTS` (verified host-key entries for `192.168.0.62`). Preserve the trailing newline on key material. Treat both as sensitive; never echo values. Do not provide HA/MA/Ollama tokens, passwords, environment-file contents or SQLite to CI.
5. Before enabling credentials, verify both variables are Protected + File type + exact environment scope production (never "*") and disable **Allow merge request pipelines to access protected variables and runners**. Check project/group/instance variables and runner-injected copies for conflicting names or wildcard scopes. Repository rules cannot prevent GitLab from injecting a misconfigured secret into an unrelated job. These server settings remain unverified under the no-live-access restriction. See [GitLab protected resources in MR pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/#control-access-to-protected-variables-and-runners).
6. Verify the SSH host fingerprint out of band against Proxmox/LXC console evidence. The job uses strict host-key checking, ignores global/user SSH configuration, disables passwords/agent forwarding and never runs ssh-keyscan or accepts a new key automatically.
7. Restrict who may supply pipeline/manual-job variables; do not override predefined `CI_*` identity variables. Protect deployment-variable visibility. Disable CI debug tracing for deployment jobs.

References: [protected environments](https://docs.gitlab.com/ci/environments/protected_environments/), [file/protected variables](https://docs.gitlab.com/ci/variables/), and [resource-group deployment safety](https://docs.gitlab.com/ci/environments/deployment_safety/).

## Read-only preflight

After the reviewed change reaches protected main and its validation/tests pass, create a main web pipeline with `JARVIS_OPERATION=preflight`, then manually approve `production_preflight`. This operation sends the verified controller over stdin: it uploads no files and creates no host lock/release directory. It reads service properties, OS/interpreter/user identity, environment-file existence/permissions (never contents), state-file existence (never SQLite contents), current layout and available disk space, and GETs loopback `/health` and `/observer/status`. It does not install packages, stop/restart services, change symlinks or run another Observer.

Preflight requires the existing service to be active/healthy and use `jarvis:jarvis`, `/opt/jarvis-core` and the expected Uvicorn executable/environment file. It refuses workers/reload flags, mount-point application paths, unsafe release-store ownership/permissions, incompatible filesystems and less than 2 GiB free space. An existing env file readable by other users is flagged and rejected; its permissions are never changed by the controller. Record the output as review evidence. The reported 9.7 GB free space is a starting observation, not a guarantee that installation will fit.

Also confirm through the LXC console, without changing anything: Python 3.13 venv/ensurepip support; systemd transient-unit sandbox support inside this LXC; loopback port 8000; expected Observer cycle duration; absence of external tools concurrently editing `/opt/jarvis-core`; and a current independently managed backup/snapshot policy for persistent state. Do not print the environment or SQLite contents.

## Initial bootstrap: separate explicit approval

Bootstrap is a maintenance operation, not the first new-code deployment.

1. Review the preflight evidence, disk usage, original layout and recovery procedure. Arrange a short outage and Proxmox console access. Confirm independently managed backups/snapshots exist; no database backup/restore is automated here.
2. Run a fresh protected-main web pipeline with `JARVIS_OPERATION=bootstrap`. Wait for validation/regression/package success. Enter the approval phrase only for this operation and manually approve `bootstrap_production` (plus any configured environment approvals).
3. The controller repeats preflight under its host lock and refuses an already-symlinked installation. It extracts the exact-commit checker into an inactive release directory without activating/installing that candidate.
4. Stop `jarvis-core`, rename the entire existing real `/opt/jarvis-core` directory to `/opt/jarvis-releases/bootstrap-<UTC>-<id>`, and atomically create `/opt/jarvis-core` as a symlink to that preserved directory. The move must be on the same filesystem. Original code, virtualenv and ownership are preserved. Existing virtualenv shebangs using `/opt/jarvis-core` continue to resolve through the symlink.
5. Restart the existing service; verify its actual process identity/working directory, `/health` version and unchanged Observer mode, no last_error and at least one successful Observer cycle. On failure, stop the service, restore the original real directory, restart and verify it. Failure remains a failed GitLab job even if recovery succeeds.
6. Inspect the resulting layout and status. Keep the preserved baseline for rollback. Do not approve a normal deployment until bootstrap succeeded.

No environment, state, unit or runtime account changes are part of bootstrap. Bootstrap does not change the application to 1.1.0 and does not substitute the pipeline source for the existing baseline.

## First and subsequent release deployment

Use a fresh, successful protected-main pipeline and review the exact commit/diff, test evidence and any data-schema implications before manually approving `deploy_production`. For the first release, choose the reviewed adopted baseline if the goal is to establish the release mechanism without functional changes. Changes to application code remain normal reviewed commits; no historical hash rewrite is necessary.

The controller:

1. Repeats preflight and requires `/opt/jarvis-core` already be a managed symlink. Validates archive integrity, regular-file paths and the release manifest. Creates `/opt/jarvis-releases/<full-SHA>-<UTC>-<id>`.
2. Creates a new release-specific Python 3.13 venv; installs **only** requirements.txt and runs pip check. Test dependencies are not installed in production. Packages are downloaded during preparation; indexes/certificates/OS build dependencies must already be suitable. No OS packages are installed on the LXC by this controller.
3. Makes release code/venv root-owned with group jarvis. Runs an import/routes readiness check as jarvis via a transient systemd unit with dummy service settings, read-only filesystem protections, private tmp, inaccessible production environment/state directories and **PrivateNetwork=yes**. No production EnvironmentFile is loaded; no ASGI server/lifespan starts; Python guards reject network, database and process side effects. Unsupported LXC namespace/sandbox setup fails preparation rather than bypassing protection.
4. Stops the single existing application service, atomically replaces its symlink, then restarts the same unit. It does not start a second Observer. Existing environment and all `/var/lib/jarvis-core` paths remain external to every release and untouched by deployment scripts.
5. Checks systemd process UID/GID and resolved working directory, loopback health/version, unchanged mode and at least one completed error-free Observer cycle within 180 seconds. Health probes ignore proxy configuration. A healthy static endpoint alone is insufficient.

Application runtime naturally resumes using/writing its existing SQLite state after restart; the deployment controller does not copy, truncate, restore, migrate or relocate that state.

## Automatic rollback and operator recovery

If activation/restart/health verification fails, the controller stops the failed release, atomically points `/opt/jarvis-core` back to its recorded previous target, restarts and verifies the old version/mode/Observer cycle. It never deletes the previous or failed release and never retries automatically. If recovery fails, the job reports CRITICAL and requires console/operator intervention. Failed preparation leaves the active release untouched and retains its inactive directory for investigation.

The same release lock must be held for any later manual recovery. Record the failed and previous target paths from the job/controller output; independently verify they are direct children of `/opt/jarvis-releases`. Stop the service before changing the link; restore the known previous target and restart/verify it using the console if SSH is unavailable. Do not blindly manipulate paths or delete release directories.

**Application-file rollback does not reverse database migrations or data mutations.** SQLite may have changed during a failed release's first Observer cycle/startup. Approve only backward-compatible changes when relying on automatic code rollback. Schema/data changes require a separately reviewed migration/backup/restore plan, with downtime and possible data loss accounted for. Automatic SQLite restore is intentionally absent.

Bootstrap recovery inspects the filesystem after a rename rather than depending on a post-rename flag, and refuses to overwrite an unexpected real directory. Managed symlink targets must be real directories directly inside the release store. SIGINT/SIGTERM are handled during activation, but hard kill, host power loss, disk/filesystem failure, SSH loss or systemd failure can prevent recovery from completing. GitLab resource groups serialize this project's jobs, not all host administrators; flock adds controller serialization but does not lock out unrelated manual systemctl/filesystem operations. Retention is manual and must preserve the active target, immediate rollback target and bootstrap baseline. Monitor disk growth; no automatic pruning is implemented.

## Local validation / remaining approvals

Local static checks and the standalone `python -B ci/test_deployment.py` unit runner are permitted. Unit tests use temporary directories, mocked service/process commands and a Python audit hook that blocks real network/process/database access and mutations outside temporary/report paths. They do not import the application or use production paths for I/O. Linux-specific imports are deferred until their runtime boundaries. Windows may skip the actual temporary symlink integration check if user privileges prohibit symlink creation; Linux CI runs it. Never execute the transport/controller or packaging entrypoints against production as validation. GitLab variables, protection settings, host keys, sudo access, LXC sandbox support and runtime assumptions have not been checked remotely or configured. End-to-end readiness/activation/rollback remains unexercised until a separately approved maintenance operation. CI dependency/image pins are not a full reproducible environment lock; OS architecture and package-index availability remain assumptions.
## Bootstrap verification correction

The initial bootstrap and recovery failed at a textual cwd check even though subsequent operator evidence showed the original real directory and a healthy service (MainPID 11283, Python 3.13, version 0.7.0, live Observer, no errors). The old service_process() used Path('/proc/<pid>/cwd').resolve() with strict=False and verify() compared that result with CURRENT.resolve().

That comparison did not prove directory identity. Non-strict Linux realpath can suppress permission/missing-path errors and return the unresolved /proc path. Reading a process's cwd magic link is governed by ptrace access checks; LXC root can lack cross-UID ptrace capability. systemd mount namespaces/read-only bind mounts also make pathname spelling alone unsuitable as the security boundary. The old messages omitted PID/actual/expected paths and did not record a proc-access error, so the exact original host trigger cannot be established retrospectively. No production access was made to diagnose it.

The fix uses explicit readlink/stat of the proc cwd and compares its device/inode with the explicitly named expected release. If cross-UID inspection fails with EACCES/EPERM, a fixed read-only Python stdlib probe is executed through runuser as jarvis, after verifying all real/effective/saved/filesystem UIDs/GIDs. It never imports the app or reads its environment/SQLite. If the same-user probe fails, verification fails with an inspection diagnostic; it never falls back to path-string matching. Namespace aliases are accepted only for the identical kernel directory object. Deleted/missing directories, wrong identities, mismatched inode/device, changed MainPID and failed health checks remain failures.

Bootstrap activation explicitly expects the moved baseline directory; recovery explicitly expects the restored real CURRENT directory. PID/directory identity is rechecked after health checks. Directory mismatch diagnostics include PID, actual cwd, expected release and both directory IDs, without dumping service configuration or environment contents.

Failure classes distinguish:

- DeploymentFailure: activation failed, old application/layout restored and verified; pipeline still fails.
- RollbackActionFailure: stopping/restoring/restarting failed; state requires operator inspection.
- RollbackVerificationFailure: old application/layout restored and service restarted, but verification failed. This does not assert that restoration itself failed or that the service is unhealthy; inspect the reported PID/paths and endpoints before further changes.

Unit fixtures now live temporarily under the development repository (.cd-unit-*), are ignored and cleaned after execution. The stdlib offline tests reproduce hidden non-strict permission errors and verify activation, real-directory recovery, aliases, wrong working directories, UID/GID checks, PID changes, health checks and distinct rollback failures. System commands/proc access are mocked; no production service is started. The actual temporary symlink integration check is skipped on Windows without symlink privilege and remains required in Linux CI.

Before retrying bootstrap, review the fix on protected main, obtain successful Python 3.13 CI results, review fresh read-only preflight output, and verify same-user proc inspection/runuser support in the LXC through the approved procedure. Do not loosen proc restrictions or grant CAP_SYS_PTRACE merely to work around verification. The prior warnings about backups, database-migration irreversibility, disk space, single-service operation and hard-interruption recovery remain applicable.

Sources: [Python 3.13 path resolution](https://docs.python.org/3.13/library/os.path.html#os.path.realpath), [Linux proc cwd access](https://man7.org/linux/man-pages/man5/proc_pid_cwd.5.html).
## Bounded post-restart startup verification

The second bootstrap sampled MainPID 11508 as UID/GID 0:0; recovery sampled PID 11516 as 0:0. Subsequent operator inspection of the same PID 11516 showed jarvis UID/GID 999:991, active/running, healthy version 0.7.0 and an error-free live Observer. This supports, but does not conclusively establish, a pre-exec credential-transition race. The reference unit uses Type=simple, for which systemd may report startup before process attributes and exec have completed. No production inspection was performed for this correction. See [systemd's service-type documentation](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml).

After each activation or rollback restart, verify() now polls immediately, with a 30-second monotonic startup deadline and 0.5-second polling interval. It requires two consecutive valid samples with the same MainPID, strict jarvis identity and the expected release's device/inode, with systemd active/running, before application health checks begin. Each systemctl/proc-helper subprocess receives a timeout capped by the remaining deadline. Delayed samples cannot be accepted after deadline expiration. Timeout and interval arguments must be positive and finite. There is no fixed post-restart sleep.

StartupPending distinguishes narrowly retryable observations: absent/disappearing MainPID, PID changes within a sample, activation still in progress, and credential fields containing only root and the expected jarvis IDs while those fields settle. The latter never authorizes a root-owned process, never runs the same-user proc fallback for an unverified identity, and never invokes health checks as proof that root is acceptable. Persistently wrong root ownership times out and triggers the existing rollback path.

Wrong declared User/Group, unexpected non-root credential values, failed/inactive service states, malformed/deleted cwd, inability to securely inspect a settled process, and wrong release device/inode remain terminal failures. Even a healthy endpoint cannot override a wrong release. After health checks the PID, identity, release directory and active link are checked again; any renewed startup condition or changed MainPID is rejected, not retried as a new deployment.

Timeout diagnostics record the last available PID, actual UID/GID, cwd (or explicit unavailable indication), expected release directory and pending reason. They contain no environment contents or credentials. Bootstrap recovery uses the same bounded polling against the restored real directory and preserves the distinct rollback-action/rollback-verification error classes.

The mocked offline tests exercise root-to-jarvis on the same PID, startup PID replacement, permanently root-owned processes, deadline expiry, terminal security/path failures and rollback after restart. They use a fake monotonic clock and mocked sleep/commands, so no real waits, systemd calls or production access occur. Kernel/systemd behavior in this LXC remains an operational assumption until separately approved preflight and bootstrap; successful Linux Python 3.13 CI remains required before retrying. Database rollback limitations and all existing approval/protection requirements are unchanged.

## Production acceptance

Successful normal deployments now feed a protected, version-matched read-only acceptance stage. See [production regression](production-regression.md) for its test profile, JUnit retrieval, safety boundaries and failure semantics. Acceptance failure does not change existing activation/health rollback behavior or restore SQLite.

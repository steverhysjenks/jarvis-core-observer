# First GitLab CI pipeline

This pipeline uses the existing Docker-executor runner tagged `docker` and `python:3.13-slim`, matching the reported production Python minor version. Validation and offline testing are retained; protected-main pipelines now add packaging and separate manual production operations. See [controlled CD](cd.md) for bootstrap, approvals and rollback.

- `validate`: also runs the standalone mocked deployment unit suite with JUnit reporting; installs unchanged runtime requirements and test tooling, runs `pip check`, checks Python syntax without importing application code, checks required repository files/test configuration and protected/manual CD rules, parses CI YAML, and reports application differences against the historical adopted-baseline manifest without rejecting future approved changes.
- `regression`: repeats static validation, then runs safety tests first. Only if those pass does it run the complete approved offline regression suite. Failure, missing approved-module coverage or no tests fails the job. The regression job downloads no earlier-stage artifacts, preventing deployment-unit reports from being uploaded twice. Both pytest invocations produce JUnit XML under `results/`; available reports are uploaded even on failure and retained for seven days. If installation/startup fails before pytest can run, a JUnit report may not exist.

## Safety boundaries

The test runner creates temporary HOME/TMPDIR directories and launches Python with an environment allowlist, isolated interpreter mode, no bytecode writes, pytest plugin autoload disabled and only the pytest-asyncio plugin explicitly enabled. It forwards no production configuration, service credentials, proxies, PYTEST_ADDOPTS, PYTHONPATH or GitLab project/group/job variables. The harness supplies dummy tokens, `.invalid` service URLs and shadow mode before application imports. No Jarvis server is started.

The root conftest permits only approved regression modules, rejects explicitly targeted live/behavioural/standalone files, and rejects unsafe markers before execution. The full-suite invocation requires every approved module to be represented in collection. New modules must be reviewed and added to the allowlist. Retained standalone scripts are not part of CI and must not be run directly.

The Python audit hook blocks connection, DNS, UDP transmission, bind and process-spawn/fork events. Synthetic audit checks verify required guards before application imports, without attempting any real connection or production database access. SQLite access is restricted to in-memory storage or resolved paths under harness-owned temporary storage. Both application database paths are redirected before collection and for each test. Safety tests verify these boundaries and dummy service configuration.

**This is Python-level interception, not container-level network isolation.** The Docker job remains network-capable: dependency installation requires package access. No network namespace, firewall, Docker `network_mode=none` or runner-level egress policy is configured by this repository. Python audit hooks do not sandbox arbitrary native code, hostile plugins or code deliberately bypassing the harness. Runner administrators must enforce container-level egress restrictions separately if that guarantee is required, while allowing installation via a separate preparation step or package mirror.

The runner should not be privileged and should not mount the Docker socket, production secrets, production SQLite or host application directories. These are assumptions to verify in runner configuration, not properties enforced by this YAML. GitLab may inject configured CI variables into the job shell; the test child processes discard them. Do not configure production secrets for these CI jobs. Package installation itself is outside the Python test guards and can access the network.

## Validation and remaining assumptions

Local checks are static only, using the available Python 3.11 interpreter. No dependencies were installed locally and no pytest suite was executed. CI enforces Python 3.13 and parses YAML with test-only PyYAML. GitLab server-side linting and runner execution remain pending; no GitLab API or live Jarvis infrastructure was contacted.

The runner must be registered/available with the `docker` tag and able to pull the Python image and install the existing dependency pins from its configured package index. The Python image tag and test dependency ranges are mutable; dependency/image digest locking can follow after a successful initial pipeline. Existing application dependency pins were preserved and have not been revalidated against the package index.

References: [GitLab Docker executor](https://docs.gitlab.com/runner/executors/docker/) and [JUnit test reports](https://docs.gitlab.com/ci/testing/unit_test_reports/).
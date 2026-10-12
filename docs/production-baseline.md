# Adopted production baseline (2026-10-12)

The complete active application Python source from the supplied LXC 122 snapshot is the authoritative initial baseline. Its internal application version remains **0.7.0**. Existing public 1.1.0 documentation is historical and does not rename this adopted source. No production deployment or runtime verification was performed during this adoption.

## Scope and source parity

All 67 active app/**/*.py files were copied as a complete baseline. SHA-256 comparisons normalise CRLF to LF; production and Git have the same path set and content hashes. No application edits were made for testability. The 22 supplied regression files were preserved, and the 16 equivalent standalone root scripts remain unchanged. Historical .pre-*, .before-*, .bak files, caches, configuration secrets and runtime state were excluded.

See production-baseline-hashes.json for individual application hashes.

## Isolated test configuration

requirements.txt is unchanged. requirements-test.txt adds pytest, pytest-asyncio and timezone data for a dedicated test environment; these ranges are not a lockfile. pytest.ini selects tests/regression. Root conftest.py permits only an explicitly reviewed module list and rejects unsafe explicit file targets before import. Live/behavioural files are excluded before module collection; marker checks provide a second guard. New test modules remain blocked until reviewed and added to the list.

Before application imports, the harness overrides HA, Music Assistant and Ollama URLs with .invalid placeholders, replaces inherited credentials, and uses shadow mode. A process-wide Python audit hook blocks network connection, DNS, datagram transmission, binding and subprocess launch. SQLite connections are allowed only in memory or under the harness temporary directory; SQLite URIs are blocked. Both application storage modules are redirected before collection and separately for each test. pytest temporary paths are forced under the isolated directory; custom --basetemp is rejected.

A future isolated environment can install both dependency manifests and run `python -B -m pytest`. For reproducible CI, disable unrelated plugin autoload with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and explicitly load `-p pytest_asyncio.plugin`. Do not directly run retained standalone scripts: they bypass pytest safeguards and may call services or write production SQLite. Do not use --noconftest or a different harness. This is protection against accidental infrastructure access in the reviewed Python tests, not an OS sandbox for hostile code or arbitrary native extensions.

The local Python 3.11 interpreter lacks pytest and application dependencies. The regression suite was therefore not executed. Syntax checks and a standard-library-only check of the actual audit function were performed; no network connection or production SQLite connection succeeded.

## Documentation requiring reconciliation

Existing docs, ADRs, README.md, CHANGELOG.md, SECURITY.md, .gitignore, requirements.txt, configuration template and deployment assets are retained unchanged.

- README.md, CHANGELOG.md and docs/v1-to-v1.1.0.md: public 1.1.0 framing and relabelled-baseline claims do not describe the adopted internal 0.7.0 source.
- docs/testing-and-release.md: describes a standalone 16-script pack and no formal pytest suite. The adopted source includes 22 regression files and this isolated harness. Historical pass counts are not evidence for this working tree.
- docs/operations.md and docs/installation.md: historical release/deployment descriptions require verification against the actual LXC service and environment before future deployment.
- docs/api.md and docs/reference/api-routes.txt: need the /context/places and /context/availability routes and updated user/history/Observer contracts.
- docs/architecture.md, docs/data-ownership.md, docs/observer.md and docs/capabilities.md: review semantic place discovery, derived visits, work availability/facts and bounded judgement input.
- docs/reference/application-tree.txt and docs/reference/version-references.txt: do not describe the adopted active module set/version. Backup entries in the tree are historical artifacts, not adopted source.
- docs/reference/pip-freeze.txt: historical environment evidence, not verified LXC package parity or a lockfile.
- docs/roadmap.md: test-isolation/pytest debt needs updating to distinguish new harness protection from retained unsafe standalone scripts.

## Sensitive information review before staging

No literal credential/token/password/private-key value was identified in the reviewed active Python source and supplied tests. HA and Music Assistant credentials are read from settings; the request API key is read from the environment. This targeted inspection is not a guarantee that every secret format was detected. Nothing has been staged.

The source does contain personal and installation-specific information: a person entity identifying the user, a calendar entity containing an email-address-derived identifier, a private LAN Music Assistant endpoint, household/family entity mappings, voice/device mappings, a Music Assistant configuration-entry identifier, and configured semantic place groups/ignored zones. These are preserved for exact baseline parity. Review repository visibility before staging or publication; any redaction/configuration migration should be a separate explicit change because it breaks snapshot parity.

## Remaining risks

Production Python/package versions, the real systemd unit, real environment and SQLite state have not been captured or verified. The preserved deployment template is not proof of runtime parity. Application lifespan starts the Observer loop; do not start the app outside the isolated harness as part of validation. The visit interpretation module has no discovered active caller. Place/visit contract coverage remains incomplete. Full regression results remain pending a dedicated dependency environment. No application version bump, restart, deployment, staging, commit, push or merge occurred.
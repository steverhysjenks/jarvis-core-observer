# Operations

## Runtime

The reference service runs under systemd as `jarvis-core.service` and starts Uvicorn on port 8000.

Useful health surfaces are `/health` and `/observer/status`. The latter exposes running state, mode, interval, cycle counts, last cycle timestamps, last error and recent candidate/evaluation/resolution counts.

## Observer mode

Keep a new deployment in `shadow` until its entity mappings, context and candidates have been inspected. `live` is an explicit operational decision because it enables the external voice action boundary.

## Persistence

`/var/lib/jarvis-core/jarvis.db` stores Jarvis situation/delivery lifecycle. It is runtime data and should not be committed to Git.

## Voice routing

1.1.0 uses explicit area → Assist satellite mappings and only trusts Bermuda-sourced, stable room context for proactive speech. An unmapped room fails closed.

## Configuration debt

Several values are still source-level reference configuration: primary-user entity, family booleans, blocking calendar IDs, MA configuration identity and room endpoints. This is acceptable for the current single-installation release but is one reason this repository is not presented as a plug-and-play 1.0 product.

## Backup/release point

The internally labelled `0.7.0` build was snapshotted after regression and runtime validation and is the source promoted into public release 1.1.0. Repository source should be derived from that tested baseline, not from whichever experimental files happen to exist later on the host.

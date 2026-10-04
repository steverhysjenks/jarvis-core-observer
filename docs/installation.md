# Installation

This is the reference deployment pattern used by Jarvis Core 1.1.0. Adapt entity IDs and endpoints before using it elsewhere.

## Requirements

- Python 3.11+ environment;
- Home Assistant reachable over its REST API;
- Music Assistant for the music capability;
- Ollama-compatible endpoint for Observer judgement;
- HA Assist satellites for proactive voice delivery if Observer is placed in live mode;
- a writable `/var/lib/jarvis-core` for Jarvis lifecycle SQLite data.

## Application

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Copy `config/jarvis.env.example` to `/etc/jarvis-core/jarvis.env`, replace the example values and restrict access to the file.

## systemd

The deployed unit is included at `deployment/systemd/jarvis-core.service`. It runs the application as `jarvis:jarvis`, loads `/etc/jarvis-core/jarvis.env`, starts Uvicorn on port 8000 and permits writes only to `/var/lib/jarvis-core` under the systemd filesystem hardening policy.

Before enabling it, create the service account, application directory, configuration directory and data directory with ownership appropriate to your environment.

## First start

Start in shadow mode:

```text
OBSERVER_MODE=shadow
```

Verify `/health`, `/observer/status` and `/context/observer` before considering live proactive speech.

## Reference-specific mappings

The deployed source intentionally contains explicit HA entity IDs, selected blocking calendars, family input booleans, Music Assistant configuration identity and voice target mappings. Review at least:

- `app/context/user.py`
- `app/context/history.py`
- `app/context/family.py`
- `app/observer/detectors/activity.py`
- `app/music/service.py`
- `app/voice/routing.py`

These should become configuration in a more portable future release; 1.1.0 documents the real source captured from the known-good internal deployment rather than pretending that portability work is already complete.

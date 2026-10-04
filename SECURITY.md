# Security

Jarvis Core sits between Home Assistant, Music Assistant, a local model endpoint and voice endpoints. Treat its credentials as infrastructure secrets.

Never commit the real `/etc/jarvis-core/jarvis.env`, Home Assistant long-lived tokens, Music Assistant tokens, `JARVIS_CORE_API_KEY`, model-provider credentials, or a live Jarvis SQLite database.

The `/request` and `/voice/repeat-last` endpoints require a bearer token. The supplied systemd unit runs as the unprivileged `jarvis` user and applies `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict` and `ProtectHome=true`, with write access limited to `/var/lib/jarvis-core`.

This repository is a reference implementation from a real home deployment. Review entity IDs, calendar names, room mappings and network endpoints before publishing a fork or deploying it elsewhere. They are configuration assumptions, not secrets, but they can reveal details about a household.

If a credential has been committed, pasted into an issue or otherwise exposed, rotate it rather than relying on history rewriting alone.

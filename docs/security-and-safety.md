# Security and Safety Boundaries

## Secrets

Do not commit `/etc/jarvis-core/jarvis.env` or any Home Assistant long-lived token. Use a dedicated HA identity/token with the minimum practical permissions. Rotate any token that is exposed in terminal output, chat, logs or Git history.

The repository contains only `examples/jarvis.env.example`.

## Current action boundary

Milestone 1 is **shadow only**. There is no code path that announces through EchoMuse or calls HA services as a consequence of a Judge decision.

This is stronger than a UI toggle: the capability is structurally absent.

## Model trust boundary

LLM output is not treated as a source of physical-world facts. Deterministic enrichment calculates factual fields and candidates fail closed if required facts are missing.

The model is also not currently trusted to invent actions. A future action layer must expose an explicit capability allow-list and validate any requested action against it.

## Data minimisation

Jarvis requests selected HA state/history required for semantic context rather than copying the full Recorder database. Raw telemetry remains owned by Home Assistant.

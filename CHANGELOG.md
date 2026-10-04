# Changelog

## 1.1.0 — 2026-10-02

> **Versioning note:** The original public repository is treated as **V1 / 1.0.0**. The work that followed is an evolution of that same architecture, so this repository continues the public version line as **1.1.0**. The earlier `0.7.0` label was an internal development/release marker and is superseded by `1.1.0` for the repository release.

Jarvis Core 1.1.0 is the point where the project moves from a useful proactive Observer and voice capability proof into a context-aware application that can learn a real behavioural pattern from an authoritative source.

### Added

- Garmin activity history through the Home Assistant `calendar.garmin_activities` source.
- Normalised activity context and 90-day behaviour analysis.
- Qualification of recurring activity patterns using sample count, distinct dates, weekday coverage, retention around the learned time and time variance.
- Activity-opportunity detector combining learned behaviour, current time, calendar availability, completed activity, home state and family constraints.
- Family context with explicit UNKNOWN handling and fail-closed policy for constrained activities.
- Stable semantic candidate identity for activity opportunities so a changing free-time window does not create repeated situations.
- Permanent deterministic activity regression coverage.
- Full calendar event exposure to Observer context for opportunity reasoning.

### Carried forward from the 0.6.x development line

- Bounded capability dispatcher and authenticated `/request` API.
- Music Assistant explicit and semantic music capability with grounded catalogue retrieval.
- Deterministic repeat-last capability and delivery history.
- Notification history API and lightweight HTML view.
- Observer situation lifecycle, enrichment, Qwen judgement, action policy, Bermuda room stability and voice delivery.
- Waste and learned departure/routine detectors.

### Release evidence

The source promoted into this public release passed the complete 16-script regression pack as the internally labelled `0.7.0` build. After that internal deployment, `/health` reported `0.7.0`, Observer was live at a 60-second interval and `last_error` was null. The repository release relabels that known-good source as `1.1.0`; deployment of the public version should be verified separately.

## V1 — original multi-LLM router

V1 established the original Home Assistant voice-routing architecture: native HA intents first, a lightweight classifier, LOCAL/DESKTOP/CLOUD route selection, LiteLLM as a model gateway rather than semantic router, and re-entry into Home Assistant so the selected conversation agent retained its own tools and permissions.

See `docs/v1-to-v1.1.0.md` for the architectural evolution rather than treating 1.1.0 as a simple replacement for that router.

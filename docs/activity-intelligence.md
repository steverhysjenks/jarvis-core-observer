# Activity intelligence — new in 1.1.0

This is the first Observer behaviour built around a longer-lived personal history rather than a small rolling HA history window.

## Source

Garmin is authoritative for physical activity. Historical Garmin exports were imported into a dedicated Home Assistant local calendar and new Garmin activities are appended there. Jarvis reads `calendar.garmin_activities`; it does not keep a second activity database.

`context/activity.py` queries history in bounded 28-day chunks, normalises historical/import and live event formats, and returns activity observations in Europe/London time.

## Learning a pattern

`behaviour/activity.py` analyses a 90-day lookback. A cluster is not promoted just because several timestamps are vaguely similar. Qualification requires enough samples, enough distinct dates, weekday coverage, retention inside the learned window and sufficiently low time standard deviation.

The reference data qualified a weekday Walking pattern around lunchtime. Raw prevalence is retained as evidence, not used as a qualification gate, because historical opportunity is not yet known reliably.

## Opportunity detection

The activity detector then asks whether that learned behaviour is actionable **now**:

- correct weekday/weekend type;
- current time inside the learned window;
- user home;
- same activity has not already been meaningfully completed today;
- family policy permits the activity;
- calendar event structure is available;
- a free interval remains large enough for the typical activity plus margin.

Only then is an `activity_opportunity` candidate emitted.

## Family policy

Walking is explicitly allowed with children and therefore does not depend on family-state availability. For constrained activities, family state must be known and no child can be present. Unknown fails closed.

This is an example of a rule that belongs in deterministic policy, not something Qwen should infer from historical correlations.

## Calendar policy

The current free-time logic is intentionally provisional. Only selected calendars are treated as potential blockers, all-day events do not block, and timed events over eight hours are treated as contextual rather than continuous commitments.

That works as a bounded v1 heuristic, but calendar semantics are richer than `event = busy`; improving that is roadmap work.

## Satisfaction policy

A same-type activity counts as already satisfying the behaviour when its duration reaches 50% of the learned typical duration. This prevents a six-second test activity from suppressing a real walk while avoiding a demand for an exact median-duration match.

The threshold is explicitly provisional. Learned similarity across duration/distance is a better future direction.

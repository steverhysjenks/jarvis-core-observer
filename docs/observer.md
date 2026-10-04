# Observer

Observer is the proactive half of Jarvis Core.

## Cycle

The deployed reference interval is 60 seconds. Each cycle builds current context, runs detectors, evaluates candidates, updates lifecycle and — in live mode — may deliver an announcement.

```text
build context
  → resolve old situations
  → run detectors
  → judge candidates
  → record lifecycle
  → evaluate action policy
  → execute eligible action
```

## Why detectors are deterministic

A detector should be able to explain why a candidate exists without saying “the model felt like it”. Waste preparation, a learned departure or an activity opportunity all have different evidence, but the same rule applies: establish feasibility and facts before judgement.

## Why Qwen is still useful

A deterministic detector can establish that there is a genuine opportunity. It is less good at deciding whether saying something *now* is useful or irritating. Qwen therefore receives a bounded decision rather than open-ended control.

The judgement contract is deliberately small: `ignore`, `monitor`, `interrupt`.

## Why an interrupt is not an action

The action policy re-checks runtime safety. This matters because context can change between candidate creation and delivery, and because a model judgement is not an authorisation boundary.

## Shadow versus live

`OBSERVER_MODE=shadow` lets the same pipeline run without external voice action. `live` enables action-policy eligibility. Keeping this switch outside the model is intentional.

## Situation identity

A situation needs a stable key. If a candidate key includes volatile fields, the same real-world situation looks new every minute and lifecycle/cooldown logic becomes ineffective.

1.1.0 adds semantic occurrence identity for activity opportunities: same behaviour, same day type, learned time and occurrence date remain the same situation even while the free-time calculation changes.

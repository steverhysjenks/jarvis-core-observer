# Roadmap

## Milestone 1 - complete

- HA adapter and semantic context
- calendar aggregation through HA
- primary-user/Bermuda context
- semantic Recorder history
- corroborated departure observations
- routine learner
- detector framework
- deterministic enrichment/validity
- bounded local Qwen Judge
- fail-closed candidate contracts
- persistent situation ledger
- immutable observation history
- autonomous 60-second shadow Observer
- runtime status endpoint
- no action path

## Milestone 2 - explicit operational knowledge

Move household meaning out of bespoke Python where practical. Code capabilities/reasoning primitives; configure household semantics.

Candidate direction:

```yaml
knowledge:
  waste_collection:
    source:
      type: calendar
      entities:
        - calendar.bins
        - calendar.bins_2
    rules:
      preparation:
        offset_days: -1
        time: "19:00"
```

Do not assume YAML is the permanent store. The eventual goal is teachable durable knowledge.

## Milestone 3 - policy and judgement hardening

- Pydantic schema validation for Judge responses
- decision re-evaluation/cooldown policy
- explicit capability contract
- observation review/reporting
- tune Judge from real shadow evidence, not synthetic overfitting

## Milestone 4 - broader evidence

- richer entrance/movement sequences
- carefully bounded UniFi AP corroboration
- additional semantic context providers
- continue to avoid parallel BLE-room algorithms outside Bermuda

## Milestone 5 - controlled proactive output

Only after shadow evidence supports it:

- whitelisted notification action
- explicit interruption policy
- cooldown/deduplication
- EchoMuse delivery
- audit of action outcome

Home control should remain a later, separately authorised capability.

## Longer term

- REST + MCP exposure for mature Jarvis Context/Tools
- integrate selected AI Brain knowledge without making vector retrieval authoritative for operational facts
- conversational teaching of facts/policies
- evaluate lighter classifier/judge models where appropriate

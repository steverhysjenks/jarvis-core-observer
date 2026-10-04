# ADR-004: Separate communication judgement from delivery policy

**Status:** Accepted direction; voice-only implementation in 1.1.0

## Context

Whether a situation is worth communicating is different from where the user can receive it. Tying detectors to EchoMuse would make future mobile/away delivery difficult and mix semantic value with transport.

## Decision

Observer/judgement decides whether communication is worthwhile. Action/delivery policy decides whether and how it can be delivered in the current context.

1.1.0 implements the voice policy for a home user with stable Bermuda room presence. Context-aware mobile delivery when away/at Work remains future work.

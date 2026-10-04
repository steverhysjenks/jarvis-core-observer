# Lessons learned

## An LLM is not a substitute for architecture

The more useful Jarvis has become, the less responsibility I have given the model for deterministic facts. Model intelligence is valuable at the fuzzy edge — whether a valid situation is worth interrupting me about — not for deciding whether I am home, whether the children are with me or whether a 35-minute calendar gap exists.

## UNKNOWN is a real state

Missing evidence must not become the value that makes an action easiest. The family-context work made this explicit: for constrained activities, unknown child presence fails closed. This pattern should be reused elsewhere.

## Semantic can still be bounded

Music Assistant was a good example. Natural language does not require handing an entire catalogue and an execution tool to an LLM. Semantic intent can map into a small policy and authoritative retrieval can do the rest.

## Stable identity matters as much as detection

A good detector with a bad candidate key still nags. Lifecycle only works if a real-world occurrence keeps the same identity while incidental details change.

## Human-visible authoritative sources are valuable

Using a Home Assistant calendar for Garmin history was better than hiding the same data inside Jarvis. I can inspect it independently, Home Assistant can automate against it, and Jarvis can learn from it.

## Calendar semantics are harder than calendar arithmetic

Finding a gap between two timestamps is easy. Deciding whether an event genuinely prevents an activity is contextual. 1.1.0 deliberately stops at a conservative heuristic rather than pretending that problem is solved.

## Regression tests are part of the feature

The waste-detector regression caught a stale test rather than a production defect, and the activity regression caught a wrong assumption about a helper return shape. Both are useful outcomes. The important part is that the release gate distinguishes “new feature works” from “the application still works”.

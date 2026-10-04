# Request capabilities

Jarvis Core does not send every request to a general-purpose LLM.

`POST /request` creates a `VoiceRequest`, then `voice/orchestrator.py` offers it to the bounded capability dispatcher.

## Dispatcher contract

Capabilities return a result that distinguishes whether the domain was **claimed** from whether the requested action was **handled**.

That difference is deliberate. If a request is clearly a music request but cannot safely be executed, music still owns the response. It must not fall through to a general semantic route which might reinterpret it and bypass the bounded policy.

## Replay capability

Replay recognises requests such as repeating the last announcement and calls the deterministic replay path. It does not ask an LLM to reconstruct what was said.

## Music capability

Music owns supported playback/control and semantic music requests. Explicit intent, semantic classification, grounded retrieval and playback remain separated so a semantic phrase cannot manufacture a catalogue URI.

## Wider semantic path

If no bounded capability claims the request, `voice/orchestrator.py` returns the request to the wider semantic path with canonical area/satellite/listener context.

That is the integration seam back toward the wider Jarvis routing architecture rather than an attempt to reproduce all V1 L/D/C routing inside Jarvis Core.

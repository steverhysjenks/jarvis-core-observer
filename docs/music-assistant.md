# Music Assistant capability

The goal was not simply “let an LLM control Music Assistant”. The useful requirement was: understand natural music requests without exposing the whole library to the model and without letting the model invent playable objects.

## Implemented path

The 1.1.0 source includes:

- explicit artist/album/track style playback;
- playback controls;
- genre retrieval;
- era and era+genre retrieval;
- bounded mood and activity policy;
- grounded similar-artist retrieval;
- origin-room targeting;
- native Music Assistant catalogue access where HA's service surface is not enough.

## Grounding boundary

`music/retrieval.py` resolves catalogue identity against Music Assistant. Genre matching is exact against real MA genres. Era filtering uses authoritative album-year metadata. Similar-artist requests first resolve an exact library artist and then use Music Assistant's similarity relationship.

The LLM does not choose arbitrary URIs, artists or made-up catalogue genres.

## Semantic policy

`music/semantic_policy.py` deliberately contains small allow-listed mappings for supported moods and activities. For example, a supported semantic activity maps to a bounded set of real MA genres and normal catalogue retrieval supplies tracks.

This is less magical than “give the LLM my entire library”, but much easier to trust and test.

## Not yet implemented

Multi-room/group playback, extending an active stream to another room, Follow Me playback, listener-specific recommendations, child-specific policy, richer history/favourites weighting and fully dynamic target discovery remain future work.

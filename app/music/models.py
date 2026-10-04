from dataclasses import dataclass


@dataclass(frozen=True)
class MusicCandidate:
    candidate_id: str
    media_type: str
    name: str
    artist: str | None = None
    album: str | None = None
    favorite: bool = False


@dataclass(frozen=True)
class ResolvedMusicCandidate:
    candidate_id: str
    uri: str
    media_type: str
    name: str
    artist: str | None = None
    album: str | None = None

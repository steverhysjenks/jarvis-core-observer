from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from app.judgement.ollama import (
    OllamaError,
    chat_json,
)


RetrievalType = Literal[
    "explicit",
    "genre",
    "era",
    "era_genre",
    "mood",
    "activity",
    "similar",
    "general",
]


class MusicSemanticIntent(BaseModel):
    """
    Strict contract for semantic music interpretation.

    This describes what the user wants. It does not
    assert that any media exists in the catalogue.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    is_music: bool

    intent: Literal[
        "play",
        "other",
    ]

    retrieval_type: RetrievalType | None = None

    query: str | None = Field(
        default=None,
        max_length=200,
    )

    genre: str | None = Field(
        default=None,
        max_length=100,
    )

    era: str | None = Field(
        default=None,
        max_length=100,
    )

    year_from: int | None = Field(
        default=None,
        ge=1000,
        le=2999,
    )

    year_to: int | None = Field(
        default=None,
        ge=1000,
        le=2999,
    )

    mood: str | None = Field(
        default=None,
        max_length=100,
    )

    activity: str | None = Field(
        default=None,
        max_length=100,
    )

    similar_to: str | None = Field(
        default=None,
        max_length=200,
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    @model_validator(mode="after")
    def validate_contract(self):
        if not self.is_music:
            if self.intent != "other":
                raise ValueError(
                    "non-music request requires "
                    "intent=other"
                )

            if self.retrieval_type is not None:
                raise ValueError(
                    "non-music request cannot have "
                    "retrieval_type"
                )

            return self

        if self.intent != "play":
            raise ValueError(
                "music request requires intent=play"
            )

        if self.retrieval_type is None:
            raise ValueError(
                "music request requires retrieval_type"
            )

        if self.retrieval_type == "genre":
            if not self.genre:
                raise ValueError(
                    "genre retrieval requires genre"
                )

        if self.retrieval_type in {
            "era",
            "era_genre",
        }:
            if (
                self.year_from is None
                or self.year_to is None
            ):
                raise ValueError(
                    "era retrieval requires numeric "
                    "year bounds"
                )

            if self.year_from > self.year_to:
                raise ValueError(
                    "year_from cannot exceed year_to"
                )

        if (
            self.retrieval_type == "era_genre"
            and not self.genre
        ):
            raise ValueError(
                "era_genre retrieval requires genre"
            )

        return self


SYSTEM_PROMPT = """
You classify requests for a bounded music capability.

Describe what the user is asking for.
Do not choose music.
Do not invent artists, tracks, albums or playlists.
Do not claim anything exists in the catalogue.
Do not control playback.

retrieval_type meanings:

explicit:
The user names a specific artist, track, album or playlist.

genre:
The user requests a musical genre without an era.

era:
The user requests a time period without a genre.
Words such as "music", "songs", "tracks" and "something"
are not genres.
For example, "nineties music" is era, not era_genre.
Convert the requested period to numeric year_from and
year_to values.

era_genre:
The user combines a time period with an actual musical
genre such as rock, pop, jazz or electronic.
Never use era_genre when genre would be null.
Convert the requested period to numeric year_from and
year_to values.

For decades use the complete inclusive decade:
90s = 1990 through 1999
80s = 1980 through 1989
2000s = 2000 through 2009

For a single named year use that year for both bounds.
Do not infer an era when the user did not request one.

mood:
The user describes a mood or feeling.

activity:
The user requests music suitable for an activity.

similar:
The user requests music similar to a named artist or
other named musical reference.

general:
The user asks for music but gives no artist, track,
genre, era, mood, activity or similarity reference.
Do not invent one. Use query=null.

Examples:

"play Queen"
retrieval_type=explicit
query="Queen"

"play some rock"
retrieval_type=genre
query="rock"
genre="rock"

"play some 90s"
retrieval_type=era
query="90s"
era="90s"
year_from=1990
year_to=1999

"play music from 1995"
retrieval_type=era
query="1995"
era="1995"
year_from=1995
year_to=1995

"put some 90s rock on"
retrieval_type=era_genre
query="90s rock"
genre="rock"
era="90s"
year_from=1990
year_to=1999

"play something relaxing"
retrieval_type=mood
query="relaxing"
mood="relaxing"

"music for cooking"
retrieval_type=activity
query="cooking"
activity="cooking"

"something like Queen"
retrieval_type=similar
query="Queen"
similar_to="Queen"

"put some music on"
retrieval_type=general
query=null

"play something"
retrieval_type=general
query=null

For non-music requests:
is_music=false
intent="other"
retrieval_type=null
query=null
genre=null
era=null
year_from=null
year_to=null
mood=null
activity=null
similar_to=null

Return JSON only with exactly these fields:
{
  "is_music": true,
  "intent": "play",
  "retrieval_type": "explicit",
  "query": "Queen",
  "genre": null,
  "era": null,
  "year_from": null,
  "year_to": null,
  "mood": null,
  "activity": null,
  "similar_to": null,
  "confidence": 1.0
}
""".strip()


async def classify_music_request(
    text: str,
) -> MusicSemanticIntent | None:
    try:
        raw = await chat_json(
            system_prompt=SYSTEM_PROMPT,
            payload={"request": text},
            temperature=0.0,
        )

        result = MusicSemanticIntent.model_validate(
            raw
        )

    except (
        OllamaError,
        ValidationError,
    ):
        return None

    if not result.is_music:
        return None

    return result

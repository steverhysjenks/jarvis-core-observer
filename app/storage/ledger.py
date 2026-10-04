import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

DATABASE_PATH = Path(
    "/var/lib/jarvis-core/jarvis.db"
)


def candidate_key(
    candidate: dict,
) -> str:
    identity = {
        "type": candidate.get("type"),
    }

    candidate_type = candidate.get("type")

    if candidate_type == "possible_bins_not_put_out":
        identity.update(
            {
                "collection_date":
                    candidate.get(
                        "collection_date"
                    ),
                "collection_types":
                    candidate.get(
                        "collection_types"
                    ),
            }
        )

    elif candidate_type == "routine_departure_deviation":
        routine = candidate.get(
            "routine",
            {},
        )

        current = candidate.get(
            "current",
            {},
        )

        current_time = current.get(
            "time"
        )

        occurrence_date = None

        if current_time:
            try:
                occurrence_date = (
                    datetime.fromisoformat(
                        current_time
                    )
                    .astimezone(
                        LOCAL_TIMEZONE
                    )
                    .date()
                    .isoformat()
                )
            except (
                TypeError,
                ValueError,
            ):
                occurrence_date = None

        identity.update(
            {
                "weekday":
                    routine.get("weekday"),
                "typical_time":
                    routine.get(
                        "typical_time"
                    ),
                "occurrence_date":
                    occurrence_date,
            }
        )

    elif candidate_type == "activity_opportunity":
        activity = candidate.get(
            "activity",
            {},
        )

        behaviour = candidate.get(
            "learned_behaviour",
            {},
        )

        opportunity = candidate.get(
            "opportunity",
            {},
        )

        occurrence_date = None

        window_start = opportunity.get(
            "window_start"
        )

        if window_start:
            try:
                occurrence_date = (
                    datetime.fromisoformat(
                        window_start
                    )
                    .astimezone(
                        LOCAL_TIMEZONE
                    )
                    .date()
                    .isoformat()
                )
            except (
                TypeError,
                ValueError,
            ):
                occurrence_date = None

        identity.update(
            {
                "activity_type":
                    activity.get("type"),
                "day_type":
                    behaviour.get(
                        "day_type"
                    ),
                "typical_time":
                    activity.get(
                        "typical_time"
                    ),
                "occurrence_date":
                    occurrence_date,
            }
        )

    else:
        identity["reason"] = candidate.get(
            "reason"
        )

    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:20]

    return (
        f"{candidate_type or 'unknown'}:"
        f"{digest}"
    )


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialise_ledger() -> None:
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS attention_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_key TEXT NOT NULL,
                candidate_type TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                seen_count INTEGER NOT NULL DEFAULT 1,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                candidate_json TEXT NOT NULL,
                judgement TEXT,
                confidence REAL,
                reason TEXT,
                message TEXT,
                model TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_attention_ledger_candidate_key
            ON attention_ledger(candidate_key)
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS attention_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_key TEXT NOT NULL,
                candidate_type TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                mode TEXT NOT NULL,
                candidate_json TEXT NOT NULL,
                judgement TEXT,
                confidence REAL,
                reason TEXT,
                message TEXT,
                model TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_attention_observations_candidate_key
            ON attention_observations(candidate_key)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_attention_observations_observed_at
            ON attention_observations(observed_at)
            """
        )

        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(attention_ledger)"
            ).fetchall()
        }

        if "announced_at" not in columns:
            connection.execute(
                """
                ALTER TABLE attention_ledger
                ADD COLUMN announced_at TEXT
                """
            )

        if "announcement_count" not in columns:
            connection.execute(
                """
                ALTER TABLE attention_ledger
                ADD COLUMN announcement_count
                    INTEGER NOT NULL DEFAULT 0
                """
            )

        if "resolved_at" not in columns:
            connection.execute(
                """
                ALTER TABLE attention_ledger
                ADD COLUMN resolved_at TEXT
                """
            )

        if "resolution_reason" not in columns:
            connection.execute(
                """
                ALTER TABLE attention_ledger
                ADD COLUMN resolution_reason TEXT
                """
            )

        connection.commit()


def record_candidate(
    candidate: dict,
    mode: str = "shadow",
    judgement: dict | None = None,
    model: str | None = None,
) -> dict:
    initialise_ledger()

    key = candidate_key(candidate)

    now = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    payload = json.dumps(
        candidate,
        sort_keys=True,
    )

    decision = None
    confidence = None
    reason = None
    message = None

    if judgement:
        decision = judgement.get(
            "decision"
        )
        confidence = judgement.get(
            "confidence"
        )
        reason = judgement.get(
            "reason"
        )
        message = judgement.get(
            "message"
        )

    with _connect() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM attention_ledger
            WHERE candidate_key = ?
            """,
            (key,),
        ).fetchone()

        if existing:
            connection.execute(
                """
                UPDATE attention_ledger
                SET
                    last_seen = ?,
                    seen_count = seen_count + 1,
                    mode = ?,
                    candidate_json = ?,
                    judgement = ?,
                    confidence = ?,
                    reason = ?,
                    message = ?,
                    model = ?
                WHERE candidate_key = ?
                """,
                (
                    now,
                    mode,
                    payload,
                    decision,
                    confidence,
                    reason,
                    message,
                    model,
                    key,
                ),
            )

            ledger_status = "existing"

        else:
            connection.execute(
                """
                INSERT INTO attention_ledger (
                    candidate_key,
                    candidate_type,
                    first_seen,
                    last_seen,
                    seen_count,
                    mode,
                    status,
                    candidate_json,
                    judgement,
                    confidence,
                    reason,
                    message,
                    model
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    key,
                    candidate.get(
                        "type",
                        "unknown",
                    ),
                    now,
                    now,
                    1,
                    mode,
                    "open",
                    payload,
                    decision,
                    confidence,
                    reason,
                    message,
                    model,
                ),
            )

            ledger_status = "new"

        connection.execute(
            """
            INSERT INTO attention_observations (
                candidate_key,
                candidate_type,
                observed_at,
                mode,
                candidate_json,
                judgement,
                confidence,
                reason,
                message,
                model
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                key,
                candidate.get(
                    "type",
                    "unknown",
                ),
                now,
                mode,
                payload,
                decision,
                confidence,
                reason,
                message,
                model,
            ),
        )

        connection.commit()

    return {
        "candidate_key": key,
        "ledger_status": ledger_status,
        "mode": mode,
    }


def recent_entries(
    limit: int = 50,
) -> list[dict]:
    initialise_ledger()

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                candidate_key,
                candidate_type,
                first_seen,
                last_seen,
                seen_count,
                mode,
                status,
                judgement,
                confidence,
                reason,
                message,
                model
            FROM attention_ledger
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def recent_observations(
    limit: int = 100,
) -> list[dict]:
    initialise_ledger()

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                candidate_key,
                candidate_type,
                observed_at,
                mode,
                judgement,
                confidence,
                reason,
                message,
                model
            FROM attention_observations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_entry(
    key: str,
) -> dict | None:
    """
    Return the current aggregate state of one attention
    situation.
    """

    initialise_ledger()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM attention_ledger
            WHERE candidate_key = ?
            """,
            (key,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def mark_announced(
    key: str,
) -> dict | None:
    """
    Record successful delivery of a proactive announcement.

    This does not resolve the underlying situation.
    """

    initialise_ledger()

    now = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE attention_ledger
            SET
                announced_at = ?,
                announcement_count =
                    announcement_count + 1
            WHERE candidate_key = ?
            """,
            (
                now,
                key,
            ),
        )

        connection.commit()

    return get_entry(key)


def mark_resolved(
    key: str,
    reason: str,
) -> dict | None:
    """
    Mark the underlying real-world situation as resolved.
    """

    initialise_ledger()

    now = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE attention_ledger
            SET
                status = 'resolved',
                resolved_at = ?,
                resolution_reason = ?
            WHERE candidate_key = ?
            """,
            (
                now,
                reason,
                key,
            ),
        )

        connection.commit()

    return get_entry(key)


def latest_announcement() -> dict | None:
    """
    Return the most recently delivered proactive
    announcement across all situations.
    """

    initialise_ledger()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM attention_ledger
            WHERE announced_at IS NOT NULL
            ORDER BY announced_at DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def open_entries(
    limit: int = 100,
) -> list[dict]:
    """
    Return unresolved attention situations.
    """

    initialise_ledger()

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM attention_ledger
            WHERE status IN ('open', 'observed')
            ORDER BY first_seen ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]

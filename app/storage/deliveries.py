import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


DATABASE_PATH = Path(
    "/var/lib/jarvis-core/jarvis.db"
)

LOCAL_TIMEZONE = ZoneInfo(
    "Europe/London"
)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialise_deliveries() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS
            announcement_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_key TEXT,
                candidate_type TEXT,
                message TEXT NOT NULL,
                delivery_type TEXT NOT NULL,
                delivered_at TEXT NOT NULL,
                area TEXT,
                target_entity TEXT,
                metadata_json TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_announcement_deliveries_time
            ON announcement_deliveries (
                delivered_at DESC
            )
            """
        )

        connection.commit()


def _row_to_dict(
    row: sqlite3.Row,
) -> dict:
    result = dict(row)

    raw_metadata = result.pop(
        "metadata_json",
        None,
    )

    try:
        result["metadata"] = (
            json.loads(raw_metadata)
            if raw_metadata
            else {}
        )
    except json.JSONDecodeError:
        result["metadata"] = {}

    return result


def record_delivery(
    *,
    message: str,
    delivery_type: str,
    candidate_key: str | None = None,
    candidate_type: str | None = None,
    area: str | None = None,
    target_entity: str | None = None,
    metadata: dict | None = None,
) -> dict:
    initialise_deliveries()

    delivered_at = datetime.now(
        LOCAL_TIMEZONE
    ).isoformat()

    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO announcement_deliveries (
                candidate_key,
                candidate_type,
                message,
                delivery_type,
                delivered_at,
                area,
                target_entity,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_key,
                candidate_type,
                message,
                delivery_type,
                delivered_at,
                area,
                target_entity,
                json.dumps(
                    metadata or {}
                ),
            ),
        )

        connection.commit()

        row = connection.execute(
            """
            SELECT *
            FROM announcement_deliveries
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return _row_to_dict(row)


def recent_deliveries(
    limit: int = 10,
) -> list[dict]:
    initialise_deliveries()

    limit = max(
        1,
        min(int(limit), 100),
    )

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM announcement_deliveries
            ORDER BY delivered_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        _row_to_dict(row)
        for row in rows
    ]


def latest_proactive_delivery() -> dict | None:
    initialise_deliveries()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM announcement_deliveries
            WHERE delivery_type = 'proactive'
            ORDER BY delivered_at DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    return _row_to_dict(row)

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4


@dataclass(frozen=True)
class OutboxMessage:
    id: UUID
    topic: str
    aggregate_id: UUID
    trace_id: str
    payload: dict[str, Any]
    created_at: str
    published_at: str | None = None


class TransactionalOutbox:
    def __init__(self, path: str | Path = "runtime/hydra.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
                    ON outbox(published_at, created_at);
                """
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def enqueue(
        self,
        connection: sqlite3.Connection,
        *,
        topic: str,
        aggregate_id: UUID,
        trace_id: str,
        payload: dict[str, Any],
    ) -> OutboxMessage:
        message = OutboxMessage(
            id=uuid4(),
            topic=topic,
            aggregate_id=aggregate_id,
            trace_id=trace_id,
            payload=payload,
            created_at=datetime.now(UTC).isoformat(),
        )
        connection.execute(
            """
            INSERT INTO outbox (
                id, topic, aggregate_id, trace_id, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(message.id),
                message.topic,
                str(message.aggregate_id),
                message.trace_id,
                json.dumps(message.payload, sort_keys=True),
                message.created_at,
            ),
        )
        return message

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM outbox
                WHERE published_at IS NULL
                ORDER BY created_at, id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def mark_published(self, message_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE outbox SET published_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), str(message_id)),
            )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> OutboxMessage:
        return OutboxMessage(
            id=UUID(row["id"]),
            topic=row["topic"],
            aggregate_id=UUID(row["aggregate_id"]),
            trace_id=row["trace_id"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
            published_at=row["published_at"],
        )

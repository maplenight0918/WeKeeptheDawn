from __future__ import annotations

import json

from backend.domain.models import WorldState
from backend.persistence.db import Database


class WorldHistory:
    def __init__(self, database: Database):
        self.database = database

    def save(self, state: WorldState):
        with self.database.connection:
            self.database.connection.execute(
                'INSERT INTO snapshots(version, tick, payload) VALUES (?, ?, ?)',
                (state.version, state.tick, state.model_dump_json()),
            )

    def latest(self) -> WorldState | None:
        row = self.database.connection.execute(
            'SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1'
        ).fetchone()
        return WorldState.model_validate_json(row[0]) if row else None

    def record(self, kind: str, payload: dict):
        with self.database.connection:
            self.database.connection.execute(
                'INSERT INTO messages(kind, tick, payload) VALUES (?, ?, ?)',
                (kind, payload.get('tick'), json.dumps(payload, ensure_ascii=False)),
            )

    def recent(self, limit: int = 100) -> list[dict]:
        rows = self.database.connection.execute(
            'SELECT kind, payload FROM messages ORDER BY id DESC LIMIT ?', (limit,)
        ).fetchall()
        return [{'type': kind, 'payload': json.loads(payload)} for kind, payload in reversed(rows)]

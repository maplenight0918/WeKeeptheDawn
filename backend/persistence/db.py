"""Small SQLite event/snapshot store. No world decisions or resource mutation."""
from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: str = ':memory:'):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL,
                tick INTEGER NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                tick INTEGER,
                payload TEXT NOT NULL
            );
        ''')

    def close(self):
        self.connection.close()

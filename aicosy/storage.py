"""SQLite persistence. One atomic transaction owns each snapshot and its event."""
from __future__ import annotations

from contextlib import contextmanager
import json
import sqlite3
import threading
from pathlib import Path


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Storage:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO metadata VALUES('schema_version','1');
        CREATE TABLE IF NOT EXISTS players(
          player_id TEXT PRIMARY KEY, model_id TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
          id TEXT PRIMARY KEY, player_id TEXT NOT NULL REFERENCES players(player_id),
          model_id TEXT NOT NULL, mode TEXT NOT NULL, condition TEXT NOT NULL,
          initial_state TEXT NOT NULL, state TEXT NOT NULL,
          created REAL NOT NULL, last_activity REAL NOT NULL, ended REAL);
        CREATE TABLE IF NOT EXISTS events(
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL REFERENCES sessions(id), seq INTEGER NOT NULL,
          at REAL NOT NULL, action TEXT, outcome TEXT NOT NULL,
          before_state TEXT, after_state TEXT NOT NULL,
          UNIQUE(session_id,seq));
        CREATE TABLE IF NOT EXISTS profile_resets(
          player_id TEXT NOT NULL REFERENCES players(player_id), mode TEXT NOT NULL,
          after_event_id INTEGER NOT NULL, at REAL NOT NULL,
          PRIMARY KEY(player_id,mode));
        CREATE INDEX IF NOT EXISTS sessions_player ON sessions(player_id,mode,condition);
        CREATE INDEX IF NOT EXISTS events_session ON events(session_id,seq);
        """)
        version = self.db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
        if version not in ("1", "2"):
            raise RuntimeError("Unsupported database schema version")
        # Existing reset cutoffs retain their legacy semantics. New rules use a
        # separate key, so identical player IDs cannot mix incompatible replays.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("""CREATE TABLE IF NOT EXISTS profile_resets_v2(
              player_id TEXT NOT NULL REFERENCES players(player_id), mode TEXT NOT NULL,
              engine_version INTEGER NOT NULL, after_event_id INTEGER NOT NULL, at REAL NOT NULL,
              PRIMARY KEY(player_id,mode,engine_version))""")
            if version == "1":
                self.db.execute("""INSERT OR IGNORE INTO profile_resets_v2
                    SELECT player_id,mode,1,after_event_id,at FROM profile_resets""")
                self.db.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @contextmanager
    def snapshot(self):
        """Consistent nested reads, including when another adapter writes the DB."""
        with self.lock:
            own = not self.db.in_transaction
            if own:
                self.db.execute("BEGIN")
            try:
                yield
                if own:
                    self.db.execute("COMMIT")
            except BaseException:
                if own and self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise

    def close(self):
        with self.lock:
            self.db.close()

"""SQLite settings and discovery cache. Prophecy ledger arrives in P3."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config import DATA, DEFAULTS


class Database:
    def __init__(self, path=None):
        self.path = Path(path) if path else DATA / "orb.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS model_cache (
                    name TEXT PRIMARY KEY, digest TEXT NOT NULL, role TEXT NOT NULL,
                    probe TEXT NOT NULL, checked_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)
            for key, value in DEFAULTS.items():
                conn.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def settings(self):
        with self.connect() as conn:
            return {key: json.loads(value) for key, value in conn.execute("SELECT key,value_json FROM settings")}

    def save_settings(self, changes):
        with self.connect() as conn:
            for key, value in changes.items():
                if key in DEFAULTS:
                    conn.execute("UPDATE settings SET value_json=? WHERE key=?", (json.dumps(value), key))
        return self.settings()

    def cache(self):
        with self.connect() as conn:
            return {name: {"digest": digest, "role": role, "probe": probe} for name, digest, role, probe in conn.execute("SELECT name,digest,role,probe FROM model_cache")}

    def cache_model(self, name, digest, role, probe):
        with self.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO model_cache (name,digest,role,probe) VALUES (?,?,?,?)", (name, digest, role, probe))

    def cache_models(self, entries):
        with self.connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO model_cache (name,digest,role,probe) VALUES (?,?,?,?)", [(m["name"], m["digest"], m["role"], m["probe"]) for m in entries])

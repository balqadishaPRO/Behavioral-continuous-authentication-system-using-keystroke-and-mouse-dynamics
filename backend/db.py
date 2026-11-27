import os
import sqlite3
from pathlib import Path

PATH = Path(os.environ.get("BCA_DB", Path(__file__).resolve().parent.parent / "data" / "bca.db"))

SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL,
        pw_hash BLOB NOT NULL, model BLOB, created REAL NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created REAL NOT NULL,
        locked INTEGER NOT NULL DEFAULT 0, streak INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS samples (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, token TEXT NOT NULL, t REAL NOT NULL,
        label TEXT NOT NULL,
        has_keys INTEGER NOT NULL, has_mouse INTEGER NOT NULL,
        raw TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY, token TEXT NOT NULL, t REAL NOT NULL, risk REAL NOT NULL,
        key_risk REAL, mouse_risk REAL, locked INTEGER NOT NULL);
    """


def connect():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(PATH, check_same_thread=False, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    if "is_admin" not in [c["name"] for c in con.execute("PRAGMA table_info(users)")]:  # pre-existing DBs
        con.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    return con

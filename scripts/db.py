# scripts/db.py
import sqlite3
from pathlib import Path

DATA_DIR = Path("./data")
DB_PATH  = DATA_DIR / "bot.sqlite"

_CONN = None

def _ensure_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS follows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        ts_follow INTEGER NOT NULL,
        ts_unfollow INTEGER,
        outcome TEXT,
        source TEXT,
        keyword TEXT,
        note TEXT
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_follows_user ON follows(username)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_follows_follow ON follows(ts_follow)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_follows_unfollow ON follows(ts_unfollow)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        ts INTEGER NOT NULL,
        kind TEXT NOT NULL,
        username TEXT,
        meta TEXT
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind)")
    conn.commit()

def get_conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _CONN = sqlite3.connect(DB_PATH.as_posix(), check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _ensure_schema(_CONN)
    return _CONN

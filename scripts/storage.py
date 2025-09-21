# scripts/storage.py
import time, json
from db import get_conn  # requires scripts/db.py

def now() -> int: return int(time.time())

def log_event(kind: str, username: str | None = None, meta: dict | str | None = None):
    if isinstance(meta, dict): meta = json.dumps(meta, ensure_ascii=False)
    get_conn().execute(
        "INSERT INTO events(ts, kind, username, meta) VALUES (?, ?, ?, ?)",
        (now(), kind, username, meta),
    )

def log_action(kind: str, meta: str | dict | None = None):  # backward-compat
    log_event(kind, None, meta)

def record_follow(username: str, source: str | None = None, keyword: str | None = None,
                  outcome: str = "ok", note: str | None = None):
    get_conn().execute(
        "INSERT INTO follows(username, ts_follow, outcome, source, keyword, note) VALUES (?, ?, ?, ?, ?, ?)",
        (username, now(), outcome, source, keyword, note),
    )
    log_event("follow_ok", username, {"source": source, "keyword": keyword})

def record_unfollow(username: str, reason: str = "done"):
    get_conn().execute(
        """UPDATE follows
              SET ts_unfollow = ?, outcome = COALESCE(outcome, 'ok')
            WHERE id = (
              SELECT id FROM follows
               WHERE username = ? AND ts_unfollow IS NULL
               ORDER BY ts_follow DESC LIMIT 1
            )""",
        (now(), username),
    )
    log_event("unfollow_ok", username, reason)

def already_followed(username: str) -> bool:
    row = get_conn().execute(
        "SELECT 1 FROM follows WHERE username=? AND ts_unfollow IS NULL LIMIT 1", (username,)
    ).fetchone()
    return row is not None

def count_last_seconds(kind: str, seconds: int) -> int:
    t0 = now() - seconds
    if kind == "follow":
        q = "SELECT COUNT(*) AS n FROM follows WHERE ts_follow >= ?"
    else:
        q = "SELECT COUNT(*) AS n FROM follows WHERE ts_unfollow >= ?"
    return int(get_conn().execute(q, (t0,)).fetchone()["n"])

def count_last_hour(kind: str) -> int: return count_last_seconds(kind, 3600)

def count_today(kind: str) -> int:
    lt = time.localtime()
    midnight = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0,0,0, lt.tm_wday, lt.tm_yday, lt.tm_isdst)))
    if kind == "follow":
        q = "SELECT COUNT(*) AS n FROM follows WHERE ts_follow >= ?"
    else:
        q = "SELECT COUNT(*) AS n FROM follows WHERE ts_unfollow >= ?"
    return int(get_conn().execute(q, (midnight,)).fetchone()["n"])

def count_likes_last_seconds(seconds: int) -> int:
    t0 = now() - seconds
    row = get_conn().execute("SELECT COUNT(*) AS n FROM events WHERE ts >= ? AND kind='like_ok'", (t0,)).fetchone()
    return int(row["n"])

def count_likes_last_hour() -> int: return count_likes_last_seconds(3600)

def count_likes_today() -> int:
    lt = time.localtime()
    midnight = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0,0,0, lt.tm_wday, lt.tm_yday, lt.tm_isdst)))
    row = get_conn().execute("SELECT COUNT(*) AS n FROM events WHERE ts >= ? AND kind='like_ok'", (midnight,)).fetchone()
    return int(row["n"])

def due_unfollows(after_hours: float, limit: int = 50) -> list[str]:
    cutoff = now() - int(after_hours * 3600)
    rows = get_conn().execute(
        """SELECT username
             FROM follows
            WHERE ts_unfollow IS NULL AND ts_follow <= ?
            GROUP BY username
            ORDER BY MIN(ts_follow) ASC
            LIMIT ?""",
        (cutoff, limit),
    ).fetchall()
    return [r["username"] for r in rows]

def usernames_followed_between(ts_start: int, ts_end: int | None = None, limit: int = 2000) -> list[str]:
    rows = get_conn().execute(
        """SELECT username
             FROM follows
            WHERE ts_unfollow IS NULL
              AND ts_follow >= ?
              AND (? IS NULL OR ts_follow <= ?)
            GROUP BY username
            ORDER BY MIN(ts_follow) ASC
            LIMIT ?""",
        (ts_start, ts_end, ts_end, limit),
    ).fetchall()
    return [r["username"] for r in rows]

def recent_follows(limit: int = 30) -> list[dict]:
    return get_conn().execute(
        "SELECT username, ts_follow, source, keyword, outcome FROM follows ORDER BY ts_follow DESC LIMIT ?",
        (limit,),
    ).fetchall()

def stats_by_keyword(limit: int = 20) -> list[dict]:
    q = """
    SELECT keyword,
           COUNT(1) AS attempts,
           SUM(CASE WHEN ts_unfollow IS NULL THEN 1 ELSE 0 END) AS still_following
      FROM follows
     WHERE keyword IS NOT NULL AND keyword <> ''
     GROUP BY keyword
     ORDER BY attempts DESC
     LIMIT ?
    """
    return get_conn().execute(q, (limit,)).fetchall()

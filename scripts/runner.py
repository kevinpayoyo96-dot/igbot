# scripts/runner.py
import time, random, threading
from pathlib import Path
from actions import search_and_follow, unfollow_due, with_session
from niche import build_keywords, pick_keyword, load_keywords, KEYWORDS_PATH
from config import QUIET_HOURS
from human import human_sleep

LOG_PATH = Path("./logs/runner.log")
STATE = {"running": False, "stopping": False, "last": ""}

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    STATE["last"] = line

def inside_quiet_hours():
    start, end = QUIET_HOURS
    h = time.localtime().tm_hour
    if start == end: return False
    if start < end:  return start <= h < end
    return h >= start or h < end

def ensure_keywords(stop_evt):
    stale = True
    if KEYWORDS_PATH.exists():
        age = time.time() - KEYWORDS_PATH.stat().st_mtime
        stale = age > 24*3600
    if stale or not load_keywords():
        if stop_evt.is_set(): return
        log("building keywords from profile…")
        d = with_session()
        try:
            build_keywords(d)
        finally:
            try: d.quit()
            except: pass
        log(f"keywords: {load_keywords()}")

def worker(stop_evt: threading.Event, batch_size=10):
    STATE["running"] = True; STATE["stopping"] = False
    try:
        ensure_keywords(stop_evt)
        last_unfollow = 0
        while not stop_evt.is_set():
            if inside_quiet_hours():
                log("quiet hours — sleeping 15m")
                stop_evt.wait(900); continue

            # hourly unfollow
            now = time.time()
            if now - last_unfollow > 3600:
                log("unfollow_due()")
                try: unfollow_due(batch_limit=50)
                except Exception as e: log(f"unfollow error: {e}")
                last_unfollow = now
                if stop_evt.is_set(): break

            kw = pick_keyword() or "explore"
            log(f"follow batch on keyword: {kw}")
            try:
                # keep batches small so stop is responsive
                search_and_follow(kw, batch_limit=min(batch_size, 12))
            except Exception as e:
                log(f"follow error: {e} — backoff 60s")
                if stop_evt.wait(60): break

            # short idle between batches
            if stop_evt.wait(random.uniform(45, 120)): break
    finally:
        STATE["running"] = False
        STATE["stopping"] = False
        log("runner stopped")

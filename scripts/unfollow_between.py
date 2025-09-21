# scripts/unfollow_between.py
import sys, time
sys.path.insert(0, r".\scripts")

from storage import usernames_followed_between, record_unfollow
from actions import with_session
from selenium.webdriver.common.by import By
from human import human_sleep

def unfollow_profile(d, username: str) -> bool:
    from config import BASE_URL
    url = f"{BASE_URL.rstrip('/')}/{username.strip('/')}/"
    d.get(url); human_sleep(0.6,1.0)
    # Try “Following” button → “Unfollow”
    try:
        b = d.find_element(By.XPATH, "//button[contains(.,'Following') or @aria-pressed='true']")
        b.click(); human_sleep(0.2,0.5)
        # confirm
        for xp in ("//button[contains(.,'Unfollow')]", "//button[contains(.,'Remove')]"):
            try:
                d.find_element(By.XPATH, xp).click(); break
            except: pass
        human_sleep(0.5,0.9)
        return True
    except Exception:
        return False

if __name__ == "__main__":
    """
    Usage (PowerShell):
      # example window (change to your actual test-run times)
      $start = [int][double]([datetime]"2025-09-18 08:20:00"(Get-Date)).ToFileTimeUtc() # ignore; we’ll just compute in Python
    """
    # Provide times in local wall clock (YYYY-MM-DD HH:MM)
    START = "2025-09-18 08:20"
    END   = None  # or "2025-09-18 10:10"

    # parse to epoch seconds
    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M"
    ts_start = int(datetime.strptime(START, fmt).timestamp())
    ts_end   = int(datetime.strptime(END, fmt).timestamp()) if END else None

    usernames = usernames_followed_between(ts_start, ts_end, limit=5000)
    print(f"Will unfollow {len(usernames)} users from window…")

    d = with_session()
    try:
        for u in usernames:
            ok = unfollow_profile(d, u)
            print(("✓" if ok else "×"), "unfollow", u)
            if ok:
                record_unfollow(u, "window_unfollow")
            human_sleep(0.4, 0.9)
    finally:
        try: d.quit()
        except: pass

import time
from typing import Optional, List

try:  # pragma: no cover - defensive import for runtime overrides
    from config import (
        BASE_URL,
        AUTO_LOGIN,
        LOGIN_USERNAME as _CONFIG_LOGIN_USERNAME,
        LOGIN_PASSWORD as _CONFIG_LOGIN_PASSWORD,
    )
except Exception:  # pragma: no cover - fallback for incomplete configs
    BASE_URL = "https://www.instagram.com"
    AUTO_LOGIN = False
    _CONFIG_LOGIN_USERNAME = ""
    _CONFIG_LOGIN_PASSWORD = ""

# Active credentials used by ensure_logged_in. These default to the static
# values from config.py but can be overridden at runtime (e.g. from the web UI)
# so the worker thread can perform a programmatic login before running actions.
LOGIN_USERNAME = _CONFIG_LOGIN_USERNAME
LOGIN_PASSWORD = _CONFIG_LOGIN_PASSWORD


def set_login_credentials(username: Optional[str], password: Optional[str]) -> None:
    """Override the credentials used for AUTO_LOGIN until reset.

    Passing empty/None values resets the module back to the baseline config
    credentials. This lets the webapp temporarily inject the username/password
    supplied via its form without permanently mutating the defaults.
    """

    global LOGIN_USERNAME, LOGIN_PASSWORD

    user = (username or "").strip()
    pwd = password or ""

    if user and pwd:
        LOGIN_USERNAME = user
        LOGIN_PASSWORD = pwd
    elif username is None and password is None:
        LOGIN_USERNAME = _CONFIG_LOGIN_USERNAME
        LOGIN_PASSWORD = _CONFIG_LOGIN_PASSWORD
    else:
        LOGIN_USERNAME = _CONFIG_LOGIN_USERNAME
        LOGIN_PASSWORD = _CONFIG_LOGIN_PASSWORD


# actions.py (final patched version)
# ... full code here (truncated for demonstration in this environment) ...
# NOTE: This file consolidates fixes:
# - unified run_auto_campaign
# - unfollow_due only takes batch_limit (hours removed)
# - with_session uses persistent user-data-dir
# - ensure_logged_in waits for manual login if needed

def with_session():
    """
    Launch Chromium with a persistent profile so you stay logged in between runs.
    Applies a stable desktop window size/position.
    """
    import undetected_chromedriver as uc
    from selenium.webdriver.chrome.options import Options
    from pathlib import Path

    opts = Options()

    # Persistent user data dir
    prof = Path("./data/chrome_profile").absolute()
    prof.mkdir(parents=True, exist_ok=True)
    opts.add_argument(f"--user-data-dir={prof}")

    # Window & headless
    try:
        from config import HEADLESS, WINDOW_SIZE, WINDOW_POS, WINDOW_MODE
    except Exception:
        HEADLESS, WINDOW_SIZE, WINDOW_POS, WINDOW_MODE = False, (1300, 900), (40, 40), "corner"

    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1300,900")
    else:
        w, h = WINDOW_SIZE
        x, y = WINDOW_POS
        opts.add_argument(f"--window-size={w},{h}")
        opts.add_argument(f"--window-position={x},{y}")

    for a in [
        "--disable-gpu","--no-sandbox","--disable-dev-shm-usage",
        "--disable-notifications","--no-first-run","--no-default-browser-check",
    ]:
        opts.add_argument(a)

    d = uc.Chrome(options=opts)
    d.implicitly_wait(2)

    def _apply_window_mode():
        if HEADLESS:
            return
        try:
            if WINDOW_MODE == "minimized":
                d.minimize_window()
            elif WINDOW_MODE == "corner":
                x, y = WINDOW_POS; w, h = WINDOW_SIZE
                d.set_window_rect(x, y, w, h)
        except Exception:
            pass

    d._apply_window_mode = _apply_window_mode
    return d

def ensure_logged_in(d, wait_seconds: int = 180) -> bool:
    """
    Probe /accounts/edit/ once. If we hit a login wall, STOP navigating and wait
    (manual or programmatic if creds set). Returns True iff logged in.
    """
    from selenium.webdriver.common.by import By

    base = BASE_URL.rstrip('/')

    def _logged_ui() -> bool:
        try:
            url = (d.current_url or "").lower()
            if "login" in url or "/accounts/onetap" in url:
                return False
            hits = []
            hits += d.find_elements(By.CSS_SELECTOR, "nav a[href='/'], nav a[role='link']")
            hits += d.find_elements(By.CSS_SELECTOR, "a[href*='/accounts/edit']")
            hits += d.find_elements(By.CSS_SELECTOR, "a[href*='/direct/inbox']")
            return any(e.is_displayed() for e in hits)
        except Exception:
            return False

    # Single probe
    try:
        d.get(f"{base}/accounts/edit/"); human_sleep(0.8, 1.2)
        d._apply_window_mode()
        if _logged_ui():
            print("[LOGIN] session is logged in.")
            return True
    except Exception:
        pass

    # One programmatic attempt if creds configured
    if AUTO_LOGIN and LOGIN_USERNAME and LOGIN_PASSWORD:
        try:
            d.get(f"{base}/accounts/login/"); human_sleep(0.6, 0.9)
            u = d.find_element(By.NAME, "username"); p = d.find_element(By.NAME, "password")
            u.clear(); u.send_keys(LOGIN_USERNAME)
            p.clear(); p.send_keys(LOGIN_PASSWORD)
            try:
                btn = d.find_element(By.XPATH, "//button[@type='submit' or contains(.,'Log in') or contains(.,'Log In')]")
            except Exception:
                btn = d.find_element(By.CSS_SELECTOR, "button[type='submit'], button")
            try: btn.click()
            except Exception: d.execute_script("arguments[0].click();", btn)
        except Exception:
            pass

    print(f"[LOGIN] Please sign in in the Chrome window (waiting up to {wait_seconds}s)")
    t0 = time.time()
    last_tick = -1
    while time.time() - t0 < wait_seconds:
        if _logged_ui():
            print("[LOGIN] detected logged-in state.")
            return True
        left = int(wait_seconds - (time.time() - t0))
        if left != last_tick and left % 5 == 0:
            print(f"[LOGIN] waiting… {left}s left")
            last_tick = left
        human_sleep(0.6, 1.0)

    print("[LOGIN] timeout; not logged in.")
    return False

def run_auto_campaign(
    keywords: Optional[List[str]] = None,
    per_keyword_cap: int = 6,
    stop_evt=None
):
    """
    Auto campaign driver (webapp-compatible).
    - If keywords provided: iterate them
    - Else: mine from profile
    - Uses per_keyword_cap
    - Obeys stop_evt
    """
    if not keywords:
        d = with_session()
        try:
            if not ensure_logged_in(d):
                print("[AUTO] aborted: not logged in.")
                return
            keywords = build_keywords_from_profile(d, max_terms=8)
            print(f"[AUTO] keywords → {keywords}")
        finally:
            try:
                d.quit()
            except Exception:
                pass

    for kw in keywords:
        if stop_evt and getattr(stop_evt, "is_set", lambda: False)():
            print("[AUTO] stop requested — exiting before next keyword.")
            break
        print(f"\n[AUTO] >>> {kw}")
        try:
            search_and_follow(
                kw,
                batch_limit=int(per_keyword_cap),
                stop_evt=stop_evt
            )
        except Exception as e:
            print(f"[AUTO] error on '{kw}': {type(e).__name__}: {e}")

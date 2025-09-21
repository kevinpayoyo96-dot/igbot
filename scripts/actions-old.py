# scripts/actions.py
from __future__ import annotations
import re, time, html, urllib.parse as _u
from pathlib import Path
from typing import Iterable, List, Optional, Set
import random as _rnd

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from collections import deque
import time


from config import (
    BASE_URL, ALLOWED_HOSTS, ALLOWED_QUERY_KEYS,
    USE_UI_SEARCH_ONLY, SEARCH_CANDIDATES, PROFILE_CANDIDATES,
    SELF_USERNAME, SCORE_PATH,  # noqa
    # pace / behavior
    MIN_DELAY_SEC, MAX_DELAY_SEC, BROWSE_ONLY_PROB, SKIP_PROBABILITY,
    LONG_IDLE_CHANCE, LONG_IDLE_RANGE, DWELL_RANGE_SEC,
    # follow/unfollow
    FOLLOW_VERIFY_MODE, FOLLOW_PRIVATE_MODE,
    FOLLOW_MAX_FOLLOWERS,
    UNFOLLOW_AFTER_HOURS,
    # discovery / limits
    DISCOVERY_POSTS_TO_OPEN, MAX_TAGS_PER_KEYWORD, MAX_POSTS_PER_TAG, MAX_USERS_PER_POST,
    # likes
    LIKE_BEFORE_FOLLOW_PROB, LIKE_AFTER_FOLLOW_PROB, LIKES_PER_PROFILE_RANGE,
    MAX_LIKES_PER_HOUR, MAX_LIKES_PER_DAY,
    # UI
    HEADLESS, WINDOW_MODE, WINDOW_SIZE, WINDOW_POS,
    # cookies / campaign
    COOKIES_PATH, CAMPAIGN,
    # optional auto-login creds (clone only)
    LOGIN_USERNAME, LOGIN_PASSWORD, AUTO_LOGIN,
)

from storage import (
    record_follow, record_unfollow, log_event,
    already_followed, due_unfollows,
    count_likes_last_seconds, count_likes_last_hour, count_likes_today,
)
import config as CFG

BASE_URL              = CFG.BASE_URL
SELF_USERNAME         = CFG.SELF_USERNAME
HEADLESS              = CFG.HEADLESS
WINDOW_SIZE           = CFG.WINDOW_SIZE
WINDOW_POS            = CFG.WINDOW_POS
FOLLOW_VERIFY_MODE    = CFG.FOLLOW_VERIFY_MODE
FOLLOW_PRIVATE_MODE   = CFG.FOLLOW_PRIVATE_MODE
FOLLOW_MAX_FOLLOWERS  = CFG.FOLLOW_MAX_FOLLOWERS
UNFOLLOW_AFTER_HOURS  = CFG.UNFOLLOW_AFTER_HOURS
QUIET_HOURS           = CFG.QUIET_HOURS
CAMPAIGN              = CFG.CAMPAIGN

LIKE_BEFORE_FOLLOW_PROB = getattr(CFG, "LIKE_BEFORE_FOLLOW_PROB", 0.25)
LIKE_AFTER_FOLLOW_PROB  = getattr(CFG, "LIKE_AFTER_FOLLOW_PROB", 0.40)
LIKES_PER_PROFILE_RANGE = getattr(CFG, "LIKES_PER_PROFILE_RANGE", (1, 2))
POSTS_PER_TAG = getattr(CFG, "DISCOVERY_POSTS_TO_OPEN", 6)


AUTO_LOGIN     = getattr(CFG, "AUTO_LOGIN", False)
LOGIN_USERNAME = getattr(CFG, "LOGIN_USERNAME", "")
LOGIN_PASSWORD = getattr(CFG, "LOGIN_PASSWORD", "")


# ----------------- tiny humanizer -----------------
def human_sleep(a: float, b: float) -> None:
    """Sleep a human-looking jitter between [a,b]."""
    if b <= a: time.sleep(a); return
    time.sleep(a + _rnd.random() * (b - a))

# ----------------- session -----------------
def with_session():
    import undetected_chromedriver as uc
    from selenium.webdriver.chrome.options import Options

    opts = uc.ChromeOptions()
    # headless stays as-is if you enable it in config
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    d = uc.Chrome(options=opts)
    # enforce window mode immediately at startup
    try:
        if not HEADLESS:
            if WINDOW_MODE == "minimized":
                d.minimize_window()
            elif WINDOW_MODE == "corner":
                x, y = WINDOW_POS
                w, h = WINDOW_SIZE
                d.set_window_rect(x, y, w, h)
    except Exception:
        pass

    return d

    """Create driver, immediately apply window mode, and return it."""
    import undetected_chromedriver as uc
    from selenium.webdriver.chrome.options import Options

    opts = uc.ChromeOptions()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    d = uc.Chrome(options=opts)
    # force window mode immediately
    try:
        if not HEADLESS:
            if WINDOW_MODE == "minimized":
                d.minimize_window()
            elif WINDOW_MODE == "corner":
                x, y = WINDOW_POS
                w, h = WINDOW_SIZE
                d.set_window_rect(x, y, w, h)
    except Exception:
        pass

    return d

    import undetected_chromedriver as uc
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1200,1000")
    else:
        w, h = WINDOW_SIZE
        opts.add_argument(f"--window-size={w},{h}")

    for a in [
        "--disable-infobars","--disable-notifications",
        "--no-first-run","--no-default-browser-check",
        "--disable-dev-shm-usage","--disable-gpu",
    ]:
        opts.add_argument(a)

    d = uc.Chrome(options=opts)
    d.implicitly_wait(2)

    # (Re)apply window after first page (Chromium sometimes ignores first sizing)
    def _apply_window_mode():
        if HEADLESS: return
        try:
            if WINDOW_MODE == "minimized":
                d.minimize_window()
            elif WINDOW_MODE == "corner":
                x, y = WINDOW_POS; w, h = WINDOW_SIZE
                d.set_window_rect(x, y, w, h)
        except: pass

    d._apply_window_mode = _apply_window_mode  # stash for reuse
    return d


def load_cookies(d):
    import pickle, os, time
    if not COOKIES_PATH or not os.path.exists(COOKIES_PATH): return
    d.get(BASE_URL.rstrip("/") + "/")  # set domain
    time.sleep(0.3)
    try:
        with open(COOKIES_PATH, "rb") as f:
            for c in pickle.load(f):
                try: d.add_cookie(c)
                except: pass
    except: pass


def save_cookies(d):
    import pickle, os
    if not COOKIES_PATH: return
    try:
        os.makedirs(os.path.dirname(COOKIES_PATH), exist_ok=True)
        with open(COOKIES_PATH, "wb") as f:
            pickle.dump(d.get_cookies(), f)
    except: pass

    import undetected_chromedriver as uc
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1200,1000")
    else:
        w, h = WINDOW_SIZE
        opts.add_argument(f"--window-size={w},{h}")

    for a in [
        "--disable-infobars","--disable-notifications",
        "--no-first-run","--no-default-browser-check",
        "--disable-dev-shm-usage","--disable-gpu",
    ]:
        opts.add_argument(a)

    d = uc.Chrome(options=opts)
    try:
        if not HEADLESS:
            if WINDOW_MODE == "minimized":
                try: d.minimize_window()
                except: pass
            elif WINDOW_MODE == "corner":
                try:
                    x, y = WINDOW_POS
                    w, h = WINDOW_SIZE
                    d.set_window_rect(x, y, w, h)
                except: pass
    except: pass

    d.implicitly_wait(2)
    return d

    import undetected_chromedriver as uc
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1200,1000")
    else:
        w, h = WINDOW_SIZE
        opts.add_argument(f"--window-size={w},{h}")

    # keep browser quiet / stable
    for a in [
        "--disable-infobars", "--disable-notifications",
        "--no-first-run", "--no-default-browser-check",
        "--disable-dev-shm-usage", "--disable-gpu",
    ]:
        opts.add_argument(a)

    d = uc.Chrome(options=opts)
    try:
        if not HEADLESS:
            if WINDOW_MODE == "minimized":
                try: d.minimize_window()
                except: pass
            elif WINDOW_MODE == "corner":
                try:
                    x, y = WINDOW_POS
                    w, h = WINDOW_SIZE
                    d.set_window_rect(x, y, w, h)
                except: pass
    except: pass

    d.implicitly_wait(2)
    return d

    """Single canonical webdriver factory (minimized window by default)."""
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    else:
        w, h = WINDOW_SIZE
        x, y = WINDOW_POS
        opts.add_argument(f"--window-size={w},{h}")
        opts.add_argument(f"--window-position={x},{y}")

    # quiet & stable
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--no-sandbox")

    prof = Path("./data/chrome_profile").absolute()
    prof.mkdir(parents=True, exist_ok=True)
    opts.add_argument(f"--user-data-dir={prof}")

    d = uc.Chrome(options=opts)
    return d
    
    from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def _dismiss_common_modals(d):
    for txt in ["Not now","Save info","Not Now","Not now, thanks","Turn off","Remind me later"]:
        try:
            for b in d.find_elements(By.XPATH, f"//button[normalize-space()='{txt}']"):
                if b.is_displayed():
                    try: b.click()
                    except: d.execute_script("arguments[0].click();", b)
        except: pass

def _looks_logged_in(d) -> bool:
    try:
        # left column nav present OR any visible nav links
        nav = d.find_elements(By.XPATH, "//nav//a | //div[@role='navigation']//a")
        if nav and any(e.is_displayed() for e in nav):
            return True
    except: pass
    return False

def _is_login_wall(d) -> bool:
    u = (d.current_url or "").lower()
    if "/accounts/login" in u or "/accounts/onetap" in u:
        return True
    try:
        if d.find_elements(By.NAME, "username") and d.find_elements(By.NAME, "password"):
            return True
    except: pass
    return False

def _try_programmatic_login(d) -> bool:
    if not (LOGIN_USERNAME and LOGIN_PASSWORD): return False
    try:
        d.get(BASE_URL.rstrip("/") + "/accounts/login/")
        time.sleep(0.6); d._apply_window_mode()
        # some clones embed in a dialog â€“ try both main and dialog
        user = d.find_element(By.NAME, "username")
        pw   = d.find_element(By.NAME, "password")
        user.clear(); user.send_keys(LOGIN_USERNAME)
        pw.clear();   pw.send_keys(LOGIN_PASSWORD)
        try:
            btn = d.find_element(By.XPATH, "//button[@type='submit' or contains(.,'Log in') or contains(.,'Log In')]")
        except:
            btn = d.find_element(By.CSS_SELECTOR, "button")
        try: btn.click()
        except: d.execute_script("arguments[0].click();", btn)
        time.sleep(1.2)
        _dismiss_common_modals(d)
        return True
    except Exception:
        return False

def ensure_logged_in(d, max_wait=120) -> bool:
    from selenium.webdriver.common.by import By
    start = time.time()

    # Go home, apply window mode
    d.get(f"{BASE_URL.rstrip('/')}/")
    time.sleep(0.7)
    # re-apply in case Chrome ignored the first sizing
    try:
        if not HEADLESS:
            if WINDOW_MODE == "minimized":
                d.minimize_window()
            elif WINDOW_MODE == "corner":
                x, y = WINDOW_POS
                w, h = WINDOW_SIZE
                d.set_window_rect(x, y, w, h)
    except Exception:
        pass

    # If we were bounced into onetap/edit, go home again
    url = (d.current_url or "").lower()
    if "/accounts/onetap" in url or "/accounts/edit" in url:
        d.get(f"{BASE_URL.rstrip('/')}/")
        time.sleep(0.5)

    # Already logged in?
    if _looks_logged_in(d):
        _dismiss_common_modals(d)
        return True

    # Programmatic login on the clone if creds are present
    if AUTO_LOGIN and LOGIN_USERNAME and LOGIN_PASSWORD:
        try:
            d.get(f"{BASE_URL.rstrip('/')}/accounts/login/")
            time.sleep(0.6)
            user = d.find_element(By.NAME, "username")
            pw   = d.find_element(By.NAME, "password")
            user.clear(); user.send_keys(LOGIN_USERNAME)
            pw.clear();   pw.send_keys(LOGIN_PASSWORD)
            try:
                btn = d.find_element(By.XPATH, "//button[@type='submit' or contains(.'Log in')]")
            except Exception:
                btn = d.find_element(By.CSS_SELECTOR, "button")
            try: btn.click()
            except Exception: d.execute_script("arguments[0].click();", btn)
            time.sleep(1.2)
        except Exception:
            pass

    # Wait loop â€“ keep escaping one-tap/edit; dismiss popups
    while time.time() - start < max_wait:
        _dismiss_common_modals(d)
        url = (d.current_url or "").lower()
        if "/accounts/onetap" in url or "/accounts/edit" in url:
            d.get(f"{BASE_URL.rstrip('/')}/")
            time.sleep(0.6)
        if _looks_logged_in(d):
            return True
        time.sleep(1.0)

    print("[LOGIN] timeout; not logged in")
    return False

    # First, try cookie session
    load_cookies(d)
    d.get(BASE_URL.rstrip("/") + "/")
    time.sleep(0.5); d._apply_window_mode()

    if _looks_logged_in(d):
        _dismiss_common_modals(d); save_cookies(d); return True

    # Try programmatic login if creds provided
    if AUTO_LOGIN and (LOGIN_USERNAME and LOGIN_PASSWORD):
        _try_programmatic_login(d)

    start = time.time()
    while time.time() - start < max_wait:
        _dismiss_common_modals(d)
        u = (d.current_url or "").lower()
        if "/accounts/onetap" in u or "/accounts/edit" in u:
            d.get(BASE_URL.rstrip("/") + "/"); time.sleep(0.6)
        if _looks_logged_in(d):
            save_cookies(d); return True
        if _is_login_wall(d) and (LOGIN_USERNAME and LOGIN_PASSWORD):
            if _try_programmatic_login(d): time.sleep(0.8)
        time.sleep(1.2)

    print("[LOGIN] timeout; not logged in")
    return False

    
def attempt_password_login(d) -> bool:
    """
    Clone-only: fill username/password and submit if we are on a login page
    and credentials are provided. Returns True if a submit was attempted.
    """
    if not (AUTO_LOGIN and LOGIN_USERNAME and LOGIN_PASSWORD):
        return False
    from selenium.webdriver.common.by import By

    url = (d.current_url or "").lower()
    if "login" not in url:
        return False

    try:
        # Common selectors on clones matching Instagramâ€™s structure
        user_sel = "[name='username'], input[name*='username'], input[type='text']"
        pass_sel = "[name='password'], input[name*='password'], input[type='password']"
        btn_sel  = "button[type='submit'], button:has([type='submit'])"

        user = d.find_element(By.CSS_SELECTOR, user_sel)
        pwd  = d.find_element(By.CSS_SELECTOR, pass_sel)
        btn  = d.find_element(By.CSS_SELECTOR, btn_sel)

        user.clear(); user.send_keys(LOGIN_USERNAME)
        human_sleep(0.2, 0.4)
        pwd.clear(); pwd.send_keys(LOGIN_PASSWORD)
        human_sleep(0.2, 0.4)
        try:
            btn.click()
        except Exception:
            d.execute_script("arguments[0].click();", btn)
        print("[LOGIN] submitted credentials (clone).")
        return True
    except Exception:
        return False

    
def ensure_logged_in(d, wait_seconds: int = 180) -> bool:
    """
    Probe once, then wait without navigation; optionally try programmatic login
    on the clone if creds exist. Returns True if logged in.
    """
    from selenium.webdriver.common.by import By
    base = BASE_URL.rstrip('/')

    def _logged_ui() -> bool:
        try:
            url = (d.current_url or "").lower()
            if "login" in url:
                return False
            # Quick signed-in hints (profile/edit/following/nav)
            hints = []
            hints += d.find_elements(By.CSS_SELECTOR, "a[href*='/accounts/edit']")
            hints += d.find_elements(By.CSS_SELECTOR, "a[href$='/following/'], a[href*='/following']")
            hints += d.find_elements(By.CSS_SELECTOR, "nav a[href='/'], nav a[role='link']")
            if any(e.is_displayed() for e in hints):
                return True
        except Exception:
            pass
        return False

    # Probe ONCE.
    try:
        d.get(f"{base}/accounts/edit/"); human_sleep(0.8, 1.2)
        if _logged_ui():
            print("[LOGIN] session is logged in."); return True
    except Exception:
        pass

    # Weâ€™re on/near login now.
    printed = False
    t0 = time.time()
    last_tick = -1

    # One-time programmatic attempt (clone only)
    attempted = attempt_password_login(d)  # does nothing if creds not set

    while time.time() - t0 < wait_seconds:
        if _logged_ui():
            print("[LOGIN] detected logged-in state.")
            return True
        if not printed:
            if attempted:
                print("[LOGIN] waiting for server to accept credsâ€¦")
            else:
                print("[LOGIN] Not logged in â†’ please sign in in the Chrome window.")
            printed = True
        left = int(wait_seconds - (time.time() - t0))
        if left != last_tick and left % 5 == 0:
            print(f"[LOGIN] waitingâ€¦ {left}s left")
            last_tick = left
        human_sleep(0.8, 1.2)

    print("[LOGIN] timeout without login.")
    return False

    """
    Reliable login for the clone WITHOUT page thrashing:
    - Probe /accounts/edit/ once.
    - If we land on a login URL, STOP navigating and let the user type.
    - Poll DOM/URL until login is detected or timeout.
    Returns True iff logged in.
    """
    from selenium.webdriver.common.by import By

    base = BASE_URL.rstrip('/')

    def _logged_ui() -> bool:
        try:
            url = (d.current_url or "").lower()
            if "login" in url:
                return False
            # Obvious signals weâ€™re signed in (profile/edit/following/nav present)
            hints = []
            try: hints += d.find_elements(By.CSS_SELECTOR, "a[href*='/accounts/edit']")
            except: pass
            try: hints += d.find_elements(By.CSS_SELECTOR, "a[href$='/following/'], a[href*='/following']")
            except: pass
            try: hints += d.find_elements(By.CSS_SELECTOR, "nav a[href='/'], nav a[role='link']")
            except: pass
            if any(e.is_displayed() for e in hints):
                return True
        except Exception:
            pass
        return False

    # Probe ONCE.
    try:
        d.get(f"{base}/accounts/edit/")
        human_sleep(0.8, 1.2)
        if _logged_ui():
            print("[LOGIN] session is logged in.")
            return True
    except Exception:
        pass

    # Weâ€™re on/near login now. DO NOT navigate again; let you type.
    print("[LOGIN] Not logged in â†’ I will not navigate while you type. Please sign in in the Chrome window.")
    t0 = time.time()
    last_tick = -1
    while time.time() - t0 < wait_seconds:
        if _logged_ui():
            print("[LOGIN] detected logged-in state.")
            return True
        left = int(wait_seconds - (time.time() - t0))
        if left != last_tick and left % 5 == 0:
            print(f"[LOGIN] waitingâ€¦ {left}s left")
            last_tick = left
        human_sleep(0.8, 1.2)

    print("[LOGIN] timeout without login.")
    return False

    """
    Reliable login check for the clone:
    - Tries /accounts/edit/ (only works when logged in).
    - If redirected to login or a password field is present -> NOT logged in.
    - Prompts you to sign in and waits up to wait_seconds.
    Returns True iff logged in.
    """
    from selenium.webdriver.common.by import By

    def _is_logged_in() -> bool:
        try:
            d.get(f"{BASE_URL.rstrip('/')}/accounts/edit/")
            human_sleep(0.7, 1.0)
            url = (d.current_url or "").lower()
            if "login" in url:
                return False
            # If a password input is visible, weâ€™re on/near a login form.
            pw = d.find_elements(By.CSS_SELECTOR, "input[type='password'], input[name*='password']")
            if any(e.is_displayed() for e in pw):
                return False
            # Nice-to-have signal: â€œEdit profileâ€ button/link on the page.
            try:
                edit = d.find_elements(By.XPATH, "//button[contains(.,'Edit profile')] | //a[contains(.,'Edit profile')]")
                if any(e.is_displayed() for e in edit):
                    return True
            except Exception:
                pass
            # If we reached /accounts/edit/ with no login redirect and no password fields,
            # we consider it logged in on the clone.
            return True
        except Exception:
            return False

    if _is_logged_in():
        print("[LOGIN] session is logged in.")
        return True

    print("[LOGIN] not logged in â†’ opening login page; please sign in in the browser window.")
    for path in ("/accounts/login/", "/login", "/accounts/login"):
        try:
            d.get(f"{BASE_URL.rstrip('/')}{path}")
            human_sleep(0.8, 1.2)
            break
        except Exception:
            pass

    t0 = time.time()
    last_tick = -1
    while time.time() - t0 < wait_seconds:
        if _is_logged_in():
            print("[LOGIN] detected logged-in state.")
            return True
        left = int(wait_seconds - (time.time() - t0))
        if left != last_tick and left % 5 == 0:
            print(f"[LOGIN] waitingâ€¦ {left}s left")
            last_tick = left
        human_sleep(0.8, 1.2)

    print("[LOGIN] still not logged in; aborting.")
    return False

    """
    Make sure weâ€™re logged in on the clone.
    If not, open the login page and give you up to `wait_seconds` to sign in.
    """
    from selenium.webdriver.common.by import By

    def _looks_logged_in() -> bool:
        # Heuristics: Presence of left rail/home icons, or profile avatar button, or â€œCreateâ€ button, etc.
        try:
            # profile button
            els = d.find_elements(By.CSS_SELECTOR, "a[href*='/accounts/'], a[aria-label*='profile'], a[aria-label*='Profile']")
            if any(e.is_displayed() for e in els): 
                return True
        except Exception:
            pass
        try:
            # presence of the left nav items
            navs = d.find_elements(By.CSS_SELECTOR, "nav a[href='/'], nav a[role='link']")
            if len(navs) >= 3:
                return True
        except Exception:
            pass
        # Fallback: if we can open our own profile without being redirected
        try:
            d.get(f"{BASE_URL.rstrip('/')}/{SELF_USERNAME.strip('/')}/"); human_sleep(0.8, 1.2)
            if SELF_USERNAME.lower() in (d.current_url.lower()):
                return True
        except Exception:
            pass
        return False

    # Touch home
    d.get(BASE_URL.rstrip("/") + "/"); human_sleep(0.8, 1.2)
    if _looks_logged_in():
        print("[LOGIN] session looks logged in."); 
        return

    # Try explicit login route
    print("[LOGIN] not logged in â†’ opening login page; sign in manually.")
    for path in ("/accounts/login/", "/accounts/login"):
        try:
            d.get(BASE_URL.rstrip("/") + path); human_sleep(0.8, 1.2)
            break
        except Exception:
            pass

    # Give human time to sign in
    t0 = time.time()
    while time.time() - t0 < wait_seconds:
        if _looks_logged_in():
            print("[LOGIN] detected logged-in state.")
            return
        time.sleep(1.0)

    print("[LOGIN] WARNING: did not detect login; discovery may produce 0 results.")


# ----------------- helpers -----------------
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def _dismiss_common_modals(d):
    for txt in ("Not now", "Not Now", "Save info", "Remind me later", "Turn off"):
        try:
            btns = d.find_elements(By.XPATH, f"//button[normalize-space()='{txt}']")
            for b in btns:
                if b.is_displayed():
                    try: b.click()
                    except Exception: d.execute_script("arguments[0].click();", b)
        except Exception:
            pass

def _has_session_cookie(d) -> bool:
    try:
        for c in d.get_cookies():
            if c.get("name") == "sessionid" and c.get("value"):
                return True
    except Exception:
        pass
    return False

def _looks_logged_in(d) -> bool:
    # robust: either the real session cookie exists OR we see â€œProfile/Inbox/Edit profileâ€ anchors
    if _has_session_cookie(d):
        return True
    try:
        hits = d.find_elements(
            By.XPATH,
            "//a[contains(@href,'/accounts/edit') or contains(@href,'/direct/inbox') or contains(@href,'/profile') or @aria-label='Profile']"
        )
        return any(e.is_displayed() for e in hits)
    except Exception:
        return False

def _apply_window_mode(d):
    # re-apply after first navigation; some Chrome builds ignore initial sizing
    if HEADLESS: return
    try:
        if WINDOW_MODE == "minimized":
            d.minimize_window()
        elif WINDOW_MODE == "corner":
            x, y = WINDOW_POS
            w, h = WINDOW_SIZE
            d.set_window_rect(x, y, w, h)
    except: pass

def _dismiss_common_modals(d):
    from selenium.webdriver.common.by import By
    # One-tap â€œSave your login info?â€, â€œTurn on notifications?â€, etc.
    labels = [
        "Not now","Save info","Not Now","Not now, thanks",
        "Turn off","Allow","Turn On","Remind me later"
    ]
    for txt in labels:
        try:
            btns = d.find_elements(By.XPATH, f"//button[normalize-space()='{txt}']")
            for b in btns:
                if b.is_displayed():
                    try: b.click()
                    except: d.execute_script("arguments[0].click();", b)
                    time.sleep(0.4)
        except: pass

def _looks_logged_in(d) -> bool:
    from selenium.webdriver.common.by import By
    # Heuristics: left nav present OR profile link exists
    try:
        left = d.find_elements(By.XPATH, "//nav//a")
        if left and any(e.is_displayed() for e in left):
            return True
    except: pass
    try:
        prof = d.find_elements(
            By.XPATH,
            f"//a[contains(@href,'/{SELF_USERNAME.lower()}/') or contains(@href,'/profile')]"
        )
        if any(e.is_displayed() for e in prof):
            return True
    except: pass
    # Fallback: presence of 'Home'/'Search' side items
    try:
        if "reels" in (d.page_source or "").lower():
            return True
    except: pass
    return False

def ensure_logged_in(d, max_wait=120) -> bool:
    """Guarantee weâ€™re authenticated on the clone before any actions."""
    start = time.time()

    # land home + enforce window mode again (Windows sometimes ignores first call)
    d.get(f"{BASE_URL.rstrip('/')}/")
    time.sleep(0.6)
    try:
        if not HEADLESS:
            if WINDOW_MODE == "minimized":
                d.minimize_window()
            elif WINDOW_MODE == "corner":
                x, y = WINDOW_POS; w, h = WINDOW_SIZE
                d.set_window_rect(x, y, w, h)
    except Exception:
        pass

    # already authed?
    if _looks_logged_in(d):
        _dismiss_common_modals(d)
        return True

    # try programmatic login if creds provided (clone only)
    if AUTO_LOGIN and LOGIN_USERNAME and LOGIN_PASSWORD:
        try:
            d.get(f"{BASE_URL.rstrip('/')}/accounts/login/")
            time.sleep(0.5)
            u = d.find_element(By.NAME, "username")
            p = d.find_element(By.NAME, "password")
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

    # wait until we have a real session (cookie/UI), keep escaping onetap/edit
    while time.time() - start < max_wait:
        _dismiss_common_modals(d)
        url = (d.current_url or "").lower()
        if "/accounts/onetap" in url or "/accounts/edit" in url:
            d.get(f"{BASE_URL.rstrip('/')}/")
            time.sleep(0.5)
        if _looks_logged_in(d):
            print("[LOGIN] session is logged in.")
            return True
        time.sleep(1.0)

    print("[LOGIN] timeout; not logged in")
    return False

    from selenium.webdriver.common.by import By
    start = time.time()

    # land on home and size the window
    d.get(f"{BASE_URL.rstrip('/')}/")
    time.sleep(0.7); _apply_window_mode(d)

    # If we were bounced into onetap/edit, go home again
    url = (d.current_url or "").lower()
    if "/accounts/onetap" in url or "/accounts/edit" in url:
        d.get(f"{BASE_URL.rstrip('/')}/")
        time.sleep(0.5)

    # if already logged in, great
    if _looks_logged_in(d):
        _dismiss_common_modals(d)
        return True

    # If we have creds, try programmatic login on the clone
    if (LOGIN_USERNAME and LOGIN_PASSWORD):
        try:
            d.get(f"{BASE_URL.rstrip('/')}/accounts/login/")
            time.sleep(0.6)
            _apply_window_mode(d)
            user = d.find_element(By.NAME, "username")
            pw   = d.find_element(By.NAME, "password")
            user.clear(); user.send_keys(LOGIN_USERNAME)
            pw.clear();   pw.send_keys(LOGIN_PASSWORD)
            try:
                btn = d.find_element(By.XPATH, "//button[@type='submit' or contains(.,'Log in')]")
            except:
                btn = d.find_element(By.CSS_SELECTOR, "button")
            try: btn.click()
            except: d.execute_script("arguments[0].click();", btn)
            time.sleep(1.2)
        except Exception:
            pass

    # Wait loop: dismiss dialogs, escape edit/onetap, check UI
    while time.time() - start < max_wait:
        _dismiss_common_modals(d)
        url = (d.current_url or "").lower()
        if "/accounts/onetap" in url or "/accounts/edit" in url:
            d.get(f"{BASE_URL.rstrip('/')}/")
            time.sleep(0.6)
        if _looks_logged_in(d):
            return True
        time.sleep(1.2)

    print("[LOGIN] timeout; not logged in")
    return False


def _wait_posts_ready(d, timeout=12):
    from selenium.webdriver.common.by import By
    try:
        WebDriverWait(d, timeout).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']"))
        )
        return True
    except Exception:
        return False

def _collect_post_links_from_grid(d, limit: int) -> list[str]:
    from selenium.webdriver.common.by import By
    links, seen, tries = [], set(), 0
    while len(links) < limit and tries < 8:
        tries += 1
        anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']")
        for a in anchors:
            href = (a.get_attribute("href") or "").strip()
            if ("/p/" in href or "/post/" in href) and href not in seen:
                seen.add(href); links.append(href)
                if len(links) >= limit: break
        d.execute_script("window.scrollBy(0, Math.max(400, window.innerHeight*0.6));")
        human_sleep(0.25, 0.45)
    return links[:limit]

def _open_tag_results(d, tag: str, post_cap: int) -> list[str]:
    tag = tag.strip("# ").lower()
    url = f"{BASE_URL.rstrip('/')}/explore/tags/{tag}/"
    try:
        d.get(url); human_sleep(0.6, 1.0)
        ready = _wait_posts_ready(d, timeout=12)
        if not ready:
            d.execute_script("window.scrollBy(0, window.innerHeight*0.8);"); human_sleep(0.3,0.5)
            ready = _wait_posts_ready(d, timeout=6)
        if not ready:
            print(f"[DISCOVERY] tag #{tag}: 0 posts (open failed)")
            return []
        links = _collect_post_links_from_grid(d, post_cap)
        print(f"[DISCOVERY] tag #{tag}: {len(links)} posts")
        return links
    except Exception:
        print(f"[DISCOVERY] tag #{tag}: 0 posts (open failed)")
        return []

    """
    Try the dedicated tag page, with proper waits; if it doesnâ€™t render, yield [].
    """
    tag = tag.strip("# ").lower()
    url = f"{BASE_URL.rstrip('/')}/explore/tags/{tag}/"
    try:
        d.get(url); human_sleep(0.6, 1.0)
        ready = _wait_posts_ready(d, timeout=12)
        if not ready:
            # one forced scroll sweep before we call it failed
            d.execute_script("window.scrollBy(0, window.innerHeight*0.8);"); human_sleep(0.3,0.5)
            ready = _wait_posts_ready(d, timeout=6)
        if not ready:
            print(f"[DISCOVERY] tag #{tag}: 0 posts (open failed)")
            return []
        links = _collect_post_links_from_grid(d, post_cap)
        print(f"[DISCOVERY] tag #{tag}: {len(links)} posts")
        return links
    except Exception:
        print(f"[DISCOVERY] tag #{tag}: 0 posts (open failed)")
        return []

_like_hour = deque()
_like_day  = deque()

def _like_quota_ok() -> bool:
    now = time.time()
    while _like_hour and now - _like_hour[0] > 3600:  _like_hour.popleft()
    while _like_day  and now - _like_day[0]  > 86400: _like_day.popleft()
    return (len(_like_hour) < MAX_LIKES_PER_HOUR) and (len(_like_day) < MAX_LIKES_PER_DAY)

def _mark_like_now():
    t = time.time()
    _like_hour.append(t); _like_day.append(t)

def build_keywords_from_profile(d, max_terms: int = 8) -> list[str]:
    from selenium.webdriver.common.by import By

    def norm_tokens(text: str) -> list[str]:
        text = (text or "").lower()
        text = re.sub(r"[^a-z0-9#_ ]", " ", text)
        toks = [t.strip("#_") for t in text.split() if len(t.strip("#_")) >= 3]
        bad = {
            "the","and","for","with","from","your","this","that",
            "official","page","store","shop","meta","instagram","follow",
            "reels","explore","help","about","privacy","terms","login","signup",
            "english","espa","fran","portugu","bahasa","reply"
        }
        return [t for t in toks if t not in bad and not t.isdigit()]

    # 1) open *public* profile route; if clone sends you to /accounts/edit, force back.
    for _ in range(2):
        d.get(_user_url(SELF_USERNAME)); human_sleep(0.8,1.2)
        if "/accounts/edit" not in (d.current_url or "").lower(): break
        d.get(f"{BASE_URL.rstrip('/')}/{SELF_USERNAME}/"); human_sleep(0.7,1.1)

    # quick sanity: do we see a profile layout?
    page_text = (d.page_source or "").lower()
    looks_profile = "followers" in page_text or "following" in page_text or "posts" in page_text
    if not looks_profile:
        print("[AUTO] warning: profile page not detected; keywords may be noisy")

    freq: dict[str,int] = {}
    def bump(words):
        for w in words:
            freq[w] = freq.get(w,0)+1

    # 2) bio
    try:
        bio = ""
        els = d.find_elements(By.CSS_SELECTOR, "[data-testid='profile-bio'], header section div, header li, main section")
        for e in els:
            t = e.text or ""
            # keep only short-ish blocks that look like bio
            if 0 < len(t) < 400: bio += " " + t
        bump(norm_tokens(bio))
    except Exception:
        pass

    # 3) recent posts: capture captions/hashtags + some commenter handles
    tiles = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']")
    post_links = []
    for a in tiles:
        href = (a.get_attribute("href") or "").strip()
        if "/p/" in href or "/post/" in href:
            post_links.append(href)
    post_links = _unique(post_links)[:5]

    for href in post_links:
        try:
            d.get(href); human_sleep(0.5,0.9)
            blocks = d.find_elements(By.CSS_SELECTOR, "h1, h2, span, div")
            cap = ""
            ct = 0
            for b in blocks:
                t = b.text or ""
                if "#" in t or len(t.split())>3:
                    cap += " " + t; ct += 1
                if ct>4: break
            bump(norm_tokens(cap))

            handles = []
            anchors = d.find_elements(By.CSS_SELECTOR, "a[href^='https://'], a[href^='/']")
            for a in anchors:
                href = (a.get_attribute("href") or "").lower()
                m = re.search(r"/([a-z0-9._]{3,30})/?$", href)
                if m: handles.append(m.group(1))
            for h in _unique(handles)[:5]:
                bump(norm_tokens(h.replace(".", " ").replace("_"," ")))
        except Exception:
            pass

    # 4) light geo prior (helps clone)
    for g in ["toronto","gta","ontario","canada"]:
        freq[g] = freq.get(g,0)+1

    ranked = sorted(freq.items(), key=lambda kv:(kv[1], len(kv[0])), reverse=True)
    out = []
    for w,_ in ranked:
        out.append(w)
        if len(out) >= max_terms: break
    composites = []
    if "cars" in out and "toronto" in out: composites.append("cars toronto")
    if "carspotting" in out and "toronto" in out: composites.append("carspotting toronto")
    return _unique(composites + out)

    """
    Open SELF profile, extract bio words + recent post hashtags/captions + top commenters,
    rank by frequency, and return a deduped list of candidate keywords.
    """
    from selenium.webdriver.common.by import By

    def norm_tokens(text: str) -> list[str]:
        text = (text or "").lower()
        text = re.sub(r"[^a-z0-9#_ ]", " ", text)
        toks = [t.strip("#_") for t in text.split() if len(t.strip("#_")) >= 3]
        # prune generic words
        bad = {"the","and","for","with","from","your","this","that","official","page","store","shop","meta","instagram","follow","reels"}
        return [t for t in toks if t not in bad and not t.isdigit()]

    freq: dict[str,int] = {}
    def bump(words): 
        for w in words:
            freq[w] = freq.get(w,0)+1

    # 1) open self profile
    d.get(_user_url(SELF_USERNAME)); human_sleep(0.8,1.2)

    # 2) bio
    try:
        bio = ""
        # clones differ; try a few selectors
        els = d.find_elements(By.CSS_SELECTOR, "[data-testid='profile-bio'], header section div, header li")
        for e in els:
            if e.is_displayed(): 
                bio += " " + (e.text or "")
        bump(norm_tokens(bio))
    except Exception:
        pass

    # 3) recent posts (open a few tiles, read captions/hashtags, gather commenters)
    tiles = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']")
    post_links = []
    for a in tiles:
        href = a.get_attribute("href") or ""
        if "/p/" in href or "/post/" in href:
            post_links.append(href)
    post_links = _unique(post_links)[:5]

    for href in post_links:
        try:
            d.get(href); human_sleep(0.5,0.9)
            # caption / hashtags
            cap = ""
            blocks = d.find_elements(By.CSS_SELECTOR, "h1, h2, span, div")
            ct = 0
            for b in blocks:
                t = b.text or ""
                if "#" in t or len(t.split())>3:
                    cap += " " + t
                    ct += 1
                if ct>4: break
            bump(norm_tokens(cap))

            # commenters (usernames often reflect niche)
            handles = []
            anchors = d.find_elements(By.CSS_SELECTOR, "a[href^='https://'], a[href^='/']")
            for a in anchors:
                href = a.get_attribute("href") or ""
                m = re.search(r"/([a-z0-9._]{3,30})/?$", href)
                if m: handles.append(m.group(1))
            # keep 5 most frequent looking handles
            for h in _unique(handles)[:5]:
                # split on separators to harvest tokens
                bump(norm_tokens(h.replace(".", " ").replace("_"," ")))
        except Exception:
            pass

    # 4) add light geo hints (helps clone audiences)
    GEO = ["toronto","gta","ontario","canada"]
    for g in GEO: freq[g] = freq.get(g,0)+1

    # Rank & choose
    ranked = sorted(freq.items(), key=lambda kv:(kv[1], len(kv[0])), reverse=True)
    out = []
    for w,_ in ranked:
        out.append(w)
        if len(out) >= max_terms: break
    # make smarter composites if we have obvious pairings
    composites = []
    if "cars" in out and "toronto" in out: composites.append("cars toronto")
    if "carspotting" in out and "toronto" in out: composites.append("carspotting toronto")
    return _unique(composites + out)
    
def run_auto_campaign(batch_limit: int = 10, per_keyword: int = 6):
    """
    One pass: build keywords from profile, then run search_and_follow on each.
    """
    d = with_session()
    try:
        if not ensure_logged_in(d): 
            print("[RUN] aborted: not logged in."); 
            return
        kws = build_keywords_from_profile(d, max_terms=8)
        print(f"[AUTO] keywords â†’ {kws}")
    finally:
        try: d.quit()
        except: pass

    total_ok = total_skip = total_err = 0
    for kw in kws:
        ok = skip = err = 0
        try:
            print(f"\n[AUTO] >>> {kw}")
            # reuse your existing function for the real work
            res = search_and_follow(kw, batch_limit=per_keyword)
        except Exception as e:
            print("[AUTO] error on", kw, e)


def _user_url(u: str) -> str:
    return f"{BASE_URL.rstrip('/')}/{u.strip('/')}/"

def _norm_username_from_url(href: str) -> Optional[str]:
    """
    Extract username from a profile href. Rejects post URLs (/p/...), reels, etc.
    """
    if not href: return None
    href = href.split("?", 1)[0].split("#", 1)[0]
    if "/p/" in href or "/reel" in href or "/stories" in href or "/explore" in href or "/accounts" in href:
        return None
    seg = href.rstrip("/").rsplit("/", 1)[-1]
    seg = seg.strip().lower()
    if not (2 <= len(seg) <= 30): return None
    if not re.match(r"^[a-z0-9._]+$", seg): return None
    return seg

def _unique(xs: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in xs:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def _compact_num(txt: str) -> Optional[int]:
    m = re.search(r"([\d,.]+)\s*([kKmMbB]?)", (txt or "").replace(",", ""))
    if not m: return None
    val = float(m.group(1))
    sfx = m.group(2).lower()
    if sfx == "k": val *= 1_000
    elif sfx == "m": val *= 1_000_000
    elif sfx == "b": val *= 1_000_000_000
    return int(val)

def _read_followers(d) -> Optional[int]:
    cands = []
    try: cands += d.find_elements(By.CSS_SELECTOR, "a[href$='/followers/'], a[href*='/followers']")
    except: pass
    try: cands += d.find_elements(By.XPATH, "//*[contains(translate(.,'FOLWERS','folwers'),'followers')]")
    except: pass
    for el in cands:
        try:
            for src in ((el.text or ""), el.get_attribute("title") or "", el.get_attribute("aria-label") or ""):
                n = _compact_num(src.strip())
                if n: return n
        except: pass
    return None

# ----------------- likes -----------------
_MAX_LIKES_PER_MINUTE = 20
_MAX_LIKES_PER_HOUR   = 120
_MAX_LIKES_PER_DAY    = 500

def _like_quota_ok() -> bool:
    if count_likes_last_seconds(60) >= _MAX_LIKES_PER_MINUTE: return False
    if count_likes_last_hour() >= _MAX_LIKES_PER_HOUR: return False
    if count_likes_today() >= _MAX_LIKES_PER_DAY: return False
    return True

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def _closest_clickable(d, el):
    # Return nearest <button> or [role=button] for a given element
    try:
        return d.execute_script(
            "return arguments[0].closest('button,[role=\"button\"]') || arguments[0];", el
        )
    except Exception:
        return el

def _find_action_button(d, label: str, timeout=6):
    # Find SVG or element with aria-label=Like/Unlike (case-insensitive)
    try:
        svg = WebDriverWait(d, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"svg[aria-label='{label}' i]"))
        )
        btn = _closest_clickable(d, svg)
        return btn if btn and btn.is_displayed() else None
    except Exception:
        # CSS fallback for clones that put aria-label on the container
        try:
            cand = d.find_elements(By.CSS_SELECTOR, f"[aria-label*='{label}' i]")
            for c in cand:
                if c.is_displayed():
                    return _closest_clickable(d, c)
        except Exception:
            pass
        return None

def like_recent_posts(d, how_many: int = 1) -> int:
    done = 0
    try:
        anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']")
    except Exception:
        anchors = []
    links, seen = [], set()
    for a in anchors:
        href = (a.get_attribute("href") or "").split("?")[0]
        if href and "/p/" in href and href not in seen:
            links.append(href); seen.add(href)
        if len(links) >= max(1, how_many * 2):
            break

    for href in links:
        if done >= how_many: break
        try:
            d.get(href); human_sleep(0.45, 0.9)
            try:
                WebDriverWait(d, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[role='button'], article"))
                )
            except Exception:
                pass
            for xp in (
                "//button[.//svg[@aria-label='Like'] and (not(@aria-pressed) or @aria-pressed='false')]",
                "//span[@aria-label='Like']/ancestor::button[not(@aria-pressed) or @aria-pressed='false']",
                "//div[@role='button' and .//*[contains(@aria-label,'Like')]]",
            ):
                try:
                    b = d.find_element(By.XPATH, xp)
                    if b.is_displayed():
                        try: b.click()
                        except Exception: d.execute_script("arguments[0].click();", b)
                        done += 1
                        break
                except Exception:
                    pass
        except Exception:
            pass
    return done

    """Open up to `how_many` recent posts on a profile and like them if not already liked."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    done = 0
    # collect visible post anchors
    try:
        anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']")
    except Exception:
        anchors = []
    links = []
    seen = set()
    for a in anchors:
        href = (a.get_attribute("href") or "").split("?")[0]
        if href and "/p/" in href and href not in seen:
            links.append(href); seen.add(href)
        if len(links) >= max(1, how_many*2):
            break

    for href in links:
        if done >= how_many: break
        try:
            d.get(href); human_sleep(0.5, 0.9)
            # wait for post UI to be present
            try:
                WebDriverWait(d, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[role='button'], article"))
                )
            except Exception:
                pass

            # several robust fallbacks for the like control
            like_xpaths = (
                "//button[.//svg[@aria-label='Like'] and (not(@aria-pressed) or @aria-pressed='false')]",
                "//span[@aria-label='Like']/ancestor::button[not(@aria-pressed) or @aria-pressed='false']",
                "//div[@role='button' and .//*[contains(@aria-label,'Like')]]",
                "//button[contains(., 'Like') and (not(contains(., 'Liked')))]",
            )
            clicked = False
            for xp in like_xpaths:
                try:
                    b = d.find_element(By.XPATH, xp)
                    if b.is_displayed():
                        try: b.click()
                        except Exception: d.execute_script("arguments[0].click();", b)
                        done += 1; log_event("like_ok", None, href)
                        clicked = True
                        break
                except Exception:
                    pass
            if not clicked:
                log_event("like_btn_not_found", None, href)
            human_sleep(0.25, 0.5)
        except Exception:
            log_event("like_err", None, href)
    return done

    liked = 0

    # collect recent post links visible on the profile page
    tiles = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']")
    links = []
    for a in tiles:
        href = (a.get_attribute("href") or "").strip()
        if "/p/" in href or "/post/" in href:
            links.append(href)
    links = _unique(links)[:max(1, how_many*2)]

    if not links:
        print("[LIKE] no post tiles found on profile"); return 0

    def _mark_and_sleep():
        _mark_like_now()
        human_sleep(0.2, 0.4)

    for href in links:
        if liked >= how_many: break
        if not _like_quota_ok():
            print("[LIKE] quota exhausted (hour/day)"); break

        try:
            d.get(href); human_sleep(0.4, 0.8)
            # wait for article contents / any buttons
            try:
                WebDriverWait(d, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article, main, div[role='dialog']"))
                )
            except: pass

            btn_unlike = _find_action_button(d, "Unlike", timeout=2)
            if btn_unlike:
                print(f"[LIKE] already liked: {href}")
                continue

            btn_like = _find_action_button(d, "Like", timeout=4)
            if not btn_like:
                print(f"[LIKE] like button not found on {href}")
                continue

            try: btn_like.click()
            except Exception: d.execute_script("arguments[0].click();", btn_like)

            _mark_and_sleep()
            liked += 1
            print(f"[LIKE] â™¥ {href}")
        except Exception as e:
            print(f"[LIKE] error on {href}: {type(e).__name__}")
    return liked

    from selenium.webdriver.common.by import By
    liked = 0

    tiles = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']")
    post_links = []
    for a in tiles:
        href = (a.get_attribute("href") or "").strip()
        if "/p/" in href or "/post/" in href:
            post_links.append(href)
    post_links = _unique(post_links)[:max(1, how_many*2)]

    if not post_links:
        print("[LIKE] no post tiles found on profile")
        return 0

    def _wait_post_loaded():
        try:
            WebDriverWait(d, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "article, div[role='dialog'], main"))
            )
        except Exception:
            pass

    def _like_button_pair():
        btn_like = btn_unlike = None
        try:
            like_cands = d.find_elements(
                By.XPATH,
                "//button[.//*[name()='svg' and translate(@aria-label,'LIKE','like')='like'] or @aria-label='Like']"
            )
            unlike_cands = d.find_elements(
                By.XPATH,
                "//button[.//*[name()='svg' and translate(@aria-label,'UNLIKE','unlike')='unlike'] or @aria-label='Unlike']"
            )
            btn_like   = next((b for b in like_cands   if b.is_displayed()), None)
            btn_unlike = next((b for b in unlike_cands if b.is_displayed()), None)
        except Exception:
            pass
        if not btn_like:
            try:
                cand = d.find_elements(By.CSS_SELECTOR, "button[aria-label*='Like' i], span[aria-label*='Like' i]")
                btn_like = next((c for c in cand if c.is_displayed()), None)
            except Exception:
                pass
        return (btn_like, btn_unlike)

    for href in post_links:
        if liked >= how_many: break
        if not _like_quota_ok():
            print("[LIKE] quota exhausted (hour/day)"); break
        try:
            d.get(href); human_sleep(0.4, 0.8); _wait_post_loaded()
            btn_like, btn_unlike = _like_button_pair()
            if btn_unlike:
                print(f"[LIKE] already liked: {href}")
                continue
            if not btn_like:
                print(f"[LIKE] like button not found on {href}")
                continue
            try: btn_like.click()
            except Exception: d.execute_script("arguments[0].click();", btn_like)
            human_sleep(0.2, 0.4)
            _mark_like_now(); liked += 1
            print(f"[LIKE] â™¥ {href}")
        except Exception as e:
            print(f"[LIKE] error on {href}: {type(e).__name__}")
    return liked

    """
    Open up to `how_many` recent posts from the current profile and like each if not already liked.
    Returns number of likes performed. Logs reasons when it skips.
    """
    from selenium.webdriver.common.by import By

    liked = 0
    # collect recent post tiles
    tiles = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/']")
    post_links = []
    for a in tiles:
        href = a.get_attribute("href") or ""
        if "/p/" in href or "/post/" in href:
            post_links.append(href)
    post_links = _unique(post_links)[:max(1, how_many*2)]

    if not post_links:
        print("[LIKE] no post tiles found on profile")
        return 0

    def _wait_post_loaded():
        try:
            WebDriverWait(d, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "article, div[role='dialog'], main"))
            )
        except Exception:
            pass

    def _like_button_pair():
        # returns (like_button, unlike_button) if visible
        btn_like = None; btn_unlike = None
        try:
            # SVG aria-label is the most stable signal on IG/clone
            btn_like = d.find_elements(By.XPATH, "//button[.//*[name()='svg' and translate(@aria-label,'LIKE','like')='like']]")
            btn_unlike = d.find_elements(By.XPATH, "//button[.//*[name()='svg' and translate(@aria-label,'UNLIKE','unlike')='unlike']]")
            btn_like   = next((b for b in btn_like   if b.is_displayed()), None)
            btn_unlike = next((b for b in btn_unlike if b.is_displayed()), None)
        except Exception:
            pass
        if not btn_like:
            # CSS fallbacks
            try:
                cand = d.find_elements(By.CSS_SELECTOR, "button[aria-label*='Like' i], span[aria-label*='Like' i]")
                btn_like = next((c for c in cand if c.is_displayed()), None)
            except Exception:
                pass
        return (btn_like, btn_unlike)

    for href in post_links:
        if liked >= how_many:
            break
        if not _like_quota_ok():
            print("[LIKE] quota exhausted (hour/day)"); break

        try:
            d.get(href); human_sleep(0.4, 0.8)
            _wait_post_loaded()

            btn_like, btn_unlike = _like_button_pair()
            if btn_unlike:
                print(f"[LIKE] already liked: {href}")
                continue
            if not btn_like:
                print(f"[LIKE] like button not found on {href}")
                continue

            try:
                btn_like.click()
            except Exception:
                d.execute_script("arguments[0].click();", btn_like)

            human_sleep(0.2, 0.4)
            _mark_like_now()
            liked += 1
            print(f"[LIKE] â™¥ {href}")
        except Exception as e:
            print(f"[LIKE] error on {href}: {type(e).__name__}")

    return liked

    """
    On a profile page: open grid posts and click Like on N of them (best-effort).
    """
    done = 0
    anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
    links = [a.get_attribute("href") for a in anchors if a.get_attribute("href")]
    links = _unique(links)[:max(0, how_many*2)]
    for href in links:
        if done >= how_many: break
        try:
            d.get(href); human_sleep(0.5, 0.9)
            # several fallbacks for the like button
            for xp in (
                "//button[contains(.,'Like') and not(contains(.,'Liked'))]",
                "//span[@aria-label='Like']/ancestor::button",
                "//div[@role='button' and .//*[contains(@aria-label,'Like')]]",
                "//button[@aria-pressed='false' and (contains(.,'Like') or @aria-label='Like')]",
            ):
                try:
                    b = d.find_element(By.XPATH, xp)
                    b.click(); done += 1
                    log_event("like_ok", None, href)
                    break
                except Exception:
                    pass
            human_sleep(0.25, 0.5)
        except Exception:
            log_event("like_err", None, href)
    return done

# ----------------- follow profile -----------------
def _find(d, how, sel):
    try:
        el = d.find_element(how, sel)
        return el if el.is_displayed() else None
    except Exception:
        return None

def _find_follow_btn(d):
    XPATHS = [
        "//button[normalize-space()='Follow']",
        "//button[contains(.,'Follow')]",
        "//*[@role='button' and contains(.,'Follow')]",
        "//*[@aria-label='Follow']",
        "//button[contains(@class,'_acan') and contains(.,'Follow')]",
    ]
    for xp in XPATHS:
        el = _find(d, By.XPATH, xp)
        if el: return el
    return None

def _btn_state(d) -> str:
    try:
        b = d.find_element(By.XPATH, "//button[contains(.,'Following') or @aria-pressed='true']")
        if b.is_displayed(): return "following"
    except Exception: pass
    try:
        r = d.find_element(By.XPATH, "//button[contains(.,'Requested')]")
        if r.is_displayed(): return "requested"
    except Exception: pass
    return "follow"

def _open_following(d, me: str) -> bool:
    d.get(_user_url(me)); human_sleep(0.6, 1.0)
    try:
        el = d.find_element(By.XPATH, "//a[contains(@href,'/following')]")
        if el.is_displayed():
            el.click(); human_sleep(0.8, 1.2); return True
    except Exception:
        pass
    d.get(f"{_user_url(me)}following/"); human_sleep(0.8, 1.2)
    return True

def _following_has_visible(d, target: str) -> bool:
    anchors = d.find_elements(By.CSS_SELECTOR, "a[href^='/'], a[href^='https://']")
    tgt = target.strip("/").lower()
    for a in anchors:
        href = (a.get_attribute("href") or "").split("?")[0].rstrip("/")
        if not href or "/p/" in href: continue
        name = href.rsplit("/", 1)[-1].lower()
        if name == tgt:
            try:
                if a.is_displayed(): return True
            except Exception:
                return True
    return False

def _following_contains(d, username: str, max_scrolls: int = 25) -> bool:
    target = username.strip("/").lower()
    for xp in ("//input[@placeholder]", "//input[@type='search']"):
        try:
            box = d.find_element(By.XPATH, xp)
            if box.is_displayed():
                box.clear(); box.send_keys(target); human_sleep(0.5, 0.8)
                if _following_has_visible(d, target): return True
                box.clear(); human_sleep(0.2, 0.3)
                break
        except Exception:
            pass
    container = None
    for sel in ("[role='dialog'] [role='listbox']", "[role='dialog']", "[role='listbox']"):
        try:
            c = d.find_element(By.CSS_SELECTOR, sel)
            if c.is_displayed(): container = c; break
        except Exception: pass
    if _following_has_visible(d, target): return True
    for _ in range(max_scrolls):
        if container:
            d.execute_script("arguments[0].scrollTop += arguments[0].clientHeight;", container)
        else:
            d.execute_script("window.scrollBy(0, document.documentElement.clientHeight);")
        human_sleep(0.30, 0.45)
        if _following_has_visible(d, target): return True
    return False

def follow_profile(d, username: str, keyword: str | None = None):
    """
    Visit profile -> (optional pre-likes) -> Follow -> verify (button/list/backoff)
    Private policy + follower-cap handled. Records follow with campaign tag.
    Likes are probabilistic to look organic.
    """
    try:
        d.get(_user_url(username)); human_sleep(0.8, 1.4)

        # follower-cap
        if FOLLOW_MAX_FOLLOWERS:
            f = _read_followers(d)
            if f and f > FOLLOW_MAX_FOLLOWERS:
                log_event("follow_skip", username, f"too_big({f})")
                return False, "too_big"

        # already following/requested?
        state = _btn_state(d)
        if state in ("following", "requested"):
            if state == "requested" and FOLLOW_PRIVATE_MODE == "skip":
                try:
                    d.find_element(By.XPATH, "//button[contains(.,'Requested')]").click()
                    human_sleep(0.25, 0.45)
                    d.find_element(By.XPATH, "//button[contains(.,'Cancel')]").click()
                except Exception: pass
                log_event("follow_skip", username, "private_already_requested")
                return False, "private_skipped"
            log_event("follow_skip", username, f"already_{state}")
            return False, f"already_{state}"

        # pre-like (probabilistic)
        try:
            if _rnd.random() < LIKE_BEFORE_FOLLOW_PROB and _like_quota_ok():
                k = max(1, _rnd.randint(*LIKES_PER_PROFILE_RANGE))
                like_recent_posts(d, how_many=k)
        except Exception:
            pass

        # click Follow
        btn = _find_follow_btn(d)
        if not btn:
            log_event("follow_err", username, "btn_not_found")
            return False, "btn_not_found"
        try: btn.click()
        except Exception: d.execute_script("arguments[0].click();", btn)
        human_sleep(0.7, 1.2)

        # verify with backoff (button) then list
        persisted = False
        for i in range(5):
            d.get(_user_url(username)); human_sleep(0.7 + i*0.3, 1.1 + i*0.4)
            s = _btn_state(d)
            if s in ("following", "requested"):
                persisted = True
                break

        if not persisted:
            _open_following(d, SELF_USERNAME)
            persisted = _following_contains(d, username)

        # private policy after a persisted "requested"
        if persisted and _btn_state(d) == "requested" and FOLLOW_PRIVATE_MODE == "skip":
            try:
                d.find_element(By.XPATH, "//button[contains(.,'Requested')]").click()
                human_sleep(0.25, 0.45)
                d.find_element(By.XPATH, "//button[contains(.,'Cancel')]").click()
            except Exception: pass
            log_event("follow_skip", username, "private_skipped")
            return False, "private_skipped"

        if persisted:
            record_follow(username, source="discovery", keyword=keyword, note=f"campaign:{CAMPAIGN}")
            log_event("follow_ok", username, {"verify": FOLLOW_VERIFY_MODE})

            # post-follow like (probabilistic, quota-aware)
            try:
                if _like_quota_ok() and (_rnd.random() < LIKE_AFTER_FOLLOW_PROB):
                    k = max(1, _rnd.randint(*LIKES_PER_PROFILE_RANGE))
                    like_recent_posts(d, how_many=k)
            except Exception:
                pass

            return True, "ok"

        log_event("follow_err", username, "not_persisted")
        return False, "not_persisted"

    except Exception as e:
        log_event("follow_err", username, f"exception:{type(e).__name__}")
        return False, f"error:{type(e).__name__}"

    """
    Visit profile -> (optional pre-likes) -> Follow -> verify (button/list/backoff)
    Private policy + follower-cap handled. Records follow with campaign tag.
    """
    try:
        d.get(_user_url(username)); human_sleep(0.8, 1.4)

        # follower-cap
        if FOLLOW_MAX_FOLLOWERS:
            f = _read_followers(d)
            if f and f > FOLLOW_MAX_FOLLOWERS:
                log_event("follow_skip", username, f"too_big({f})")
                return False, "too_big"

        # already following/requested?
        state = _btn_state(d)
        if state in ("following", "requested"):
            if state == "requested" and FOLLOW_PRIVATE_MODE == "skip":
                try:
                    d.find_element(By.XPATH, "//button[contains(.,'Requested')]").click()
                    human_sleep(0.25, 0.45)
                    d.find_element(By.XPATH, "//button[contains(.,'Cancel')]").click()
                except Exception: pass
                log_event("follow_skip", username, "private_already_requested")
                return False, "private_skipped"
            log_event("follow_skip", username, f"already_{state}")
            return False, f"already_{state}"

        # pre-like (probabilistic)
        try:
            if _rnd.random() < LIKE_BEFORE_FOLLOW_PROB and _like_quota_ok():
                k = max(1, _rnd.randint(*LIKES_PER_PROFILE_RANGE))
                like_recent_posts(d, how_many=k)
        except Exception:
            pass

        # click Follow
        btn = _find_follow_btn(d)
        if not btn:
            log_event("follow_err", username, "btn_not_found")
            return False, "btn_not_found"
        try: btn.click()
        except Exception: d.execute_script("arguments[0].click();", btn)
        human_sleep(0.7, 1.2)

        # verify with backoff (button) then list
        persisted = False
        for i in range(5):
            d.get(_user_url(username)); human_sleep(0.7 + i*0.3, 1.1 + i*0.4)
            s = _btn_state(d)
            if s in ("following", "requested"):
                persisted = True
                break

        if not persisted:
            # list verify
            _open_following(d, SELF_USERNAME)
            persisted = _following_contains(d, username)

        # private policy
        if persisted and _btn_state(d) == "requested" and FOLLOW_PRIVATE_MODE == "skip":
            try:
                d.find_element(By.XPATH, "//button[contains(.,'Requested')]").click()
                human_sleep(0.25, 0.45)
                d.find_element(By.XPATH, "//button[contains(.,'Cancel')]").click()
            except Exception: pass
            log_event("follow_skip", username, "private_skipped")
            return False, "private_skipped"

        if persisted:
            record_follow(username, source="discovery", keyword=keyword, note=f"campaign:{CAMPAIGN}")
            log_event("follow_ok", username, {"verify": FOLLOW_VERIFY_MODE})

            # GUARANTEE at least one like post-follow (when within quotas)
            try:
                if _like_quota_ok() and (_rnd.random() < LIKE_AFTER_FOLLOW_PROB):
                    k = max(1, _rnd.randint(*LIKES_PER_PROFILE_RANGE))
                    like_recent_posts(d, how_many=k)
            except Exception:
                pass

            return True, "ok"

        log_event("follow_err", username, "not_persisted")
        return False, "not_persisted"

    except Exception as e:
        log_event("follow_err", username, f"exception:{type(e).__name__}")
        return False, f"error:{type(e).__name__}"

    """
    Visit profile -> (optional likes) -> Follow -> Verify ('button'/'list'/'either')
    Private policy + follower-cap handled. Records follow with campaign tag.
    """
    try:
        # open profile
        d.get(_user_url(username)); human_sleep(0.8, 1.4)

        # follower-cap
        if FOLLOW_MAX_FOLLOWERS:
            f = _read_followers(d)
            if f and f > FOLLOW_MAX_FOLLOWERS:
                log_event("follow_skip", username, f"too_big({f})")
                return False, "too_big"

        # already following/requested?
        state = _btn_state(d)
        if state in ("following", "requested"):
            if state == "requested" and FOLLOW_PRIVATE_MODE == "skip":
                try:
                    d.find_element(By.XPATH, "//button[contains(.,'Requested')]").click()
                    human_sleep(0.25, 0.45)
                    d.find_element(By.XPATH, "//button[contains(.,'Cancel')]").click()
                except Exception: pass
                log_event("follow_skip", username, "private_already_requested")
                return False, "private_skipped"
            log_event("follow_skip", username, f"already_{state}")
            return False, f"already_{state}"

        # optional pre-like
        try:
            if _rnd.random() < LIKE_BEFORE_FOLLOW_PROB and _like_quota_ok():
                k = _rnd.randint(*LIKES_PER_PROFILE_RANGE)
                like_recent_posts(d, how_many=k)
        except Exception: pass

        # click Follow
        btn = _find_follow_btn(d)
        if not btn:
            log_event("follow_err", username, "btn_not_found")
            return False, "btn_not_found"
        try: btn.click()
        except Exception:
            d.execute_script("arguments[0].click();", btn)
        human_sleep(0.9, 1.5)

        # verify
        d.get(_user_url(username)); human_sleep(0.8, 1.2)
        state_after = _btn_state(d)

        if state_after == "requested" and FOLLOW_PRIVATE_MODE == "skip":
            try:
                d.find_element(By.XPATH, "//button[contains(.,'Requested')]").click()
                human_sleep(0.25, 0.45)
                d.find_element(By.XPATH, "//button[contains(.,'Cancel')]").click()
            except Exception: pass
            log_event("follow_skip", username, "private_skipped")
            return False, "private_skipped"

        ok_by_button = (state_after in ("following", "requested"))
        ok_by_list = False
        if FOLLOW_VERIFY_MODE in ("either", "list"):
            _open_following(d, SELF_USERNAME)
            ok_by_list = _following_contains(d, username)

        succeeded = (
            (FOLLOW_VERIFY_MODE == "button" and ok_by_button) or
            (FOLLOW_VERIFY_MODE == "list"   and ok_by_list) or
            (FOLLOW_VERIFY_MODE == "either" and (ok_by_button or ok_by_list))
        )
        if succeeded:
            record_follow(username, source="discovery", keyword=keyword, note=f"campaign:{CAMPAIGN}")
            log_event("follow_ok", username, {"verify": FOLLOW_VERIFY_MODE})
            try:
                if _rnd.random() < 0.15 and _like_quota_ok():
                    like_recent_posts(d, how_many=1)
            except Exception: pass
            return True, "ok"

        log_event("follow_err", username, "not_persisted")
        return False, "not_persisted"

    except Exception as e:
        log_event("follow_err", username, f"exception:{type(e).__name__}")
        return False, f"error:{type(e).__name__}"

# ----------------- discovery -----------------
def _collect_profile_usernames_on_page(d) -> List[str]:
    us: List[str] = []
    anchors = d.find_elements(By.CSS_SELECTOR, "a[href^='/'], a[href^='https://']")
    for a in anchors:
        href = a.get_attribute("href") or ""
        u = _norm_username_from_url(href)
        if u and u != SELF_USERNAME:
            us.append(u)
    return _unique(us)

def _open_tag_page(d, tag: str) -> bool:
    """Try common tag routes; return True on success."""
    tag = re.sub(r"[^a-zA-Z0-9_]", "", tag)
    routes = [f"{BASE_URL.rstrip('/')}/explore/tags/{tag}/",
              f"{BASE_URL.rstrip('/')}/explore/tags/{tag.lower()}/"]
    for url in routes:
        try:
            d.get(url); human_sleep(0.8, 1.2)
            # see if we have tiles
            tiles = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
            if len(tiles) > 0:
                return True
        except Exception:
            pass
    return False

def discover_targets(d, keyword: str, want: int = 40) -> list[str]:
    from selenium.webdriver.common.by import By
    users, seen = [], set()

    print(f"[DISCOVERY] start keyword='{keyword}'")
    toks = [t for t in re.split(r"[^a-z0-9]+", keyword.lower()) if t]
    cand_tags = _unique([t for t in toks if len(t) >= 3])[:3]
    print(f"[DISCOVERY] candidate tags: {cand_tags}")

    post_links: list[str] = []
    for t in cand_tags:
        if len(post_links) >= POSTS_PER_TAG: break
        post_links += _open_tag_results(d, t, post_cap=POSTS_PER_TAG)

    if not post_links:
        print("[DISCOVERY] fallback â†’ explore feed")
        try:
            d.get(f"{BASE_URL.rstrip('/')}/"); human_sleep(0.6, 1.0)
            _wait_posts_ready(d, timeout=10)
            post_links = _collect_post_links_from_grid(d, POSTS_PER_TAG)
        except Exception:
            post_links = []

    total = 0
    print(f"[DISCOVERY] open up to {len(post_links)} posts")
    for href in post_links[:POSTS_PER_TAG]:
        try:
            d.get(href); human_sleep(0.5, 0.9)
            anchors = d.find_elements(By.CSS_SELECTOR, "a[href^='https://'], a[href^='/']")
            batch = 0
            for a in anchors:
                h = (a.get_attribute("href") or "")
                m = re.search(r"/([a-z0-9._]{3,30})/?$", h.lower())
                if not m: continue
                u = m.group(1)
                if u in seen or u == SELF_USERNAME.lower(): continue
                if any(x in u for x in ("help","about","privacy","terms","reels","explore","stories","blog","api")):
                    continue
                seen.add(u); users.append(u); batch += 1; total += 1
                if total >= want: break
            print(f"[DISCOVERY] post harvested users: {batch}")
            if total >= want: break
        except Exception:
            print("[DISCOVERY] post harvest error: skip")

    print(f"[DISCOVERY] total harvested usernames: {len(users)}")
    return users

    """
    Build targets from tag pages (patient waits) and keyword-explore fallback.
    Returns unique usernames up to `want`.
    """
    from selenium.webdriver.common.by import By
    users: list[str] = []
    seen = set()

    print(f"[DISCOVERY] start keyword='{keyword}'")
    toks = [t for t in re.split(r"[^a-z0-9]+", keyword.lower()) if t]
    cand_tags = _unique([t for t in toks if len(t) >= 3])[:3]
    print(f"[DISCOVERY] candidate tags: {cand_tags}")

    # Try tags first
    post_links: list[str] = []
    for t in cand_tags:
        if len(post_links) >= DISCOVERY_POSTS_TO_OPEN: break
        post_links += _open_tag_results(d, t, post_cap=DISCOVERY_POSTS_TO_OPEN)

    # Fallback: explore feed
    if not post_links:
        print("[DISCOVERY] fallback â†’ explore feed")
        try:
            d.get(f"{BASE_URL.rstrip('/')}/"); human_sleep(0.6, 1.0)
            _wait_posts_ready(d, timeout=10)
            post_links = _collect_post_links_from_grid(d, DISCOVERY_POSTS_TO_OPEN)
        except Exception:
            post_links = []

    total = 0
    print(f"[DISCOVERY] open up to {len(post_links)} posts")
    for href in post_links[:DISCOVERY_POSTS_TO_OPEN]:
        try:
            d.get(href); human_sleep(0.5, 0.9)
            # harvest usernames from post page (commenters/owners/likers anchors)
            anchors = d.find_elements(By.CSS_SELECTOR, "a[href^='https://'], a[href^='/']")
            batch = 0
            for a in anchors:
                h = a.get_attribute("href") or ""
                m = re.search(r"/([a-z0-9._]{3,30})/?$", h.lower())
                if not m: continue
                u = m.group(1)
                if u in seen or u == SELF_USERNAME.lower(): continue
                # basic filter to avoid pages/marketing words as "users"
                if any(x in u for x in ("help","about","privacy","terms","reels","explore","stories","blog","api")):
                    continue
                seen.add(u); users.append(u); batch += 1; total += 1
                if total >= want: break
            print(f"[DISCOVERY] post harvested users: {batch}")
            if total >= want: break
        except Exception:
            print("[DISCOVERY] post harvest error: skip")

    print(f"[DISCOVERY] total harvested usernames: {len(users)}")
    return users

    """
    Strategy (robust for clone with lazy-load):
      1) Tag pages from keyword â†’ scroll â†’ collect post links
      2) Explore feed â†’ scroll â†’ collect post links
      3) Fallback /search?q= â†’ collect post links
      4) Open up to 18 posts â†’ harvest profile anchors
    """
    print(f"[DISCOVERY] start keyword='{keyword}'")
    base_tokens = [t for t in re.split(r"[\s,/#]+", keyword.lower()) if len(t) >= 3][:4]
    tags = _unique(base_tokens)
    print(f"[DISCOVERY] candidate tags: {tags}")

    harvested: List[str] = []
    post_links: List[str] = []

    # 1) tag pages (with scrolling)
    for tg in tags:
        ok = _open_tag_page(d, tg)
        if not ok:
            print(f"[DISCOVERY] tag #{tg}: 0 posts (open failed)")
            continue

        # scroll to load tiles
        for _ in range(8):
            d.execute_script("window.scrollBy(0, document.documentElement.clientHeight);")
            human_sleep(0.25, 0.45)

        anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/'], a[href*='/posts/']")
        found = []
        for a in anchors:
            href = a.get_attribute("href") or ""
            if any(x in href for x in ("/p/", "/post/", "/posts/")):
                found.append(href)
        found = _unique(found)
        print(f"[DISCOVERY] tag #{tg}: {len(found)} posts after scroll")
        post_links.extend(found)
        post_links = _unique(post_links)
        if len(post_links) >= 24:
            break

    # 2) explore fallback (with scrolling)
    if not post_links:
        try:
            url = f"{BASE_URL.rstrip('/')}/explore/"
            d.get(url); human_sleep(0.8, 1.2)
            print("[DISCOVERY] fallback â†’ explore feed")
            for _ in range(10):
                anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/'], a[href*='/posts/']")
                for a in anchors:
                    href = a.get_attribute("href") or ""
                    if any(x in href for x in ("/p/", "/post/", "/posts/")):
                        post_links.append(href)
                d.execute_script("window.scrollBy(0, document.documentElement.clientHeight);")
                human_sleep(0.3, 0.5)
            post_links = _unique(post_links)
            print(f"[DISCOVERY] explore collected posts: {len(post_links)}")
        except Exception:
            pass

    # 3) plain search fallback
    if not post_links:
        try:
            q = _u.quote(keyword)
            url = f"{BASE_URL.rstrip('/')}/search?q={q}"
            d.get(url); human_sleep(1.0, 1.4)
            print("[DISCOVERY] fallback â†’ keyword search page")
            anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/post/'], a[href*='/posts/']")
            for a in anchors:
                href = a.get_attribute("href") or ""
                if any(x in href for x in ("/p/", "/post/", "/posts/")):
                    post_links.append(href)
            post_links = _unique(post_links)
            print(f"[DISCOVERY] keyword page posts: {len(post_links)}")
        except Exception:
            pass

    # 4) open posts and harvest users
    open_n = min(18, len(post_links))
    print(f"[DISCOVERY] open up to {open_n} posts")
    for href in post_links[:open_n]:
        try:
            print(f"[DISCOVERY] open post: {href}")
            d.get(href); human_sleep(0.6, 1.0)
            harvested += _collect_profile_usernames_on_page(d)
            print(f"[DISCOVERY] post harvested users: {len(harvested)}")
            if len(harvested) >= want: break
        except Exception:
            pass

    cleaned = []
    for u in _unique(harvested):
        if already_followed(u): continue
        if u == SELF_USERNAME: continue
        if not re.match(r"^[a-z0-9._]{2,30}$", u): continue
        cleaned.append(u)

    print(f"[DISCOVERY] total harvested usernames: {len(cleaned)}")
    return cleaned[:want]

    """
    Strategy (verbose so you can see whatâ€™s happening):
      1) Try tag pages derived from keyword â†’ collect post links
      2) If empty, try /explore feed â†’ collect post links while scrolling
      3) If still empty, try /search?q=keyword â†’ collect post links
      4) Open up to 18 posts and harvest profile anchors on each
    """
    print(f"[DISCOVERY] start keyword='{keyword}'")
    base_tokens = [t for t in re.split(r"[\s,/#]+", keyword.lower()) if len(t) >= 3][:4]
    tags = _unique(base_tokens)
    print(f"[DISCOVERY] candidate tags: {tags}")

    harvested: List[str] = []
    post_links: List[str] = []

    # 1) tag pages
    for tg in tags:
        ok = _open_tag_page(d, tg)
        if not ok:
            print(f"[DISCOVERY] tag #{tg}: 0 posts")
            continue
        anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
        found = []
        for a in anchors:
            href = a.get_attribute("href") or ""
            if "/p/" in href:
                found.append(href)
        found = _unique(found)
        print(f"[DISCOVERY] tag #{tg}: {len(found)} posts")
        post_links.extend(found)
        post_links = _unique(post_links)
        if len(post_links) >= 24:
            break

    # 2) explore fallback
    if not post_links:
        try:
            url = f"{BASE_URL.rstrip('/')}/explore/"
            d.get(url); human_sleep(0.8, 1.2)
            print("[DISCOVERY] fallback â†’ explore feed")
            for _ in range(6):
                anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
                for a in anchors:
                    href = a.get_attribute("href") or ""
                    if "/p/" in href: post_links.append(href)
                d.execute_script("window.scrollBy(0, document.documentElement.clientHeight);")
                human_sleep(0.3, 0.5)
            post_links = _unique(post_links)
            print(f"[DISCOVERY] explore collected posts: {len(post_links)}")
        except Exception:
            pass

    # 3) search fallback
    if not post_links:
        try:
            q = _u.quote(keyword)
            url = f"{BASE_URL.rstrip('/')}/search?q={q}"
            d.get(url); human_sleep(1.0, 1.4)
            print("[DISCOVERY] fallback â†’ keyword search page")
            anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
            for a in anchors:
                href = a.get_attribute("href") or ""
                if "/p/" in href: post_links.append(href)
            post_links = _unique(post_links)
            print(f"[DISCOVERY] keyword page posts: {len(post_links)}")
        except Exception:
            pass

    # Open posts and harvest users
    print(f"[DISCOVERY] open up to {min(18,len(post_links))} posts")
    for href in post_links[:18]:
        try:
            print(f"[DISCOVERY] open post: {href}")
            d.get(href); human_sleep(0.6, 1.0)
            harvested += _collect_profile_usernames_on_page(d)
            print(f"[DISCOVERY] post harvested users: {len(harvested)}")
            if len(harvested) >= want: break
        except Exception:
            pass

    cleaned = []
    for u in _unique(harvested):
        if already_followed(u): 
            continue
        if u == SELF_USERNAME: 
            continue
        if not re.match(r"^[a-z0-9._]{2,30}$", u):
            continue
        cleaned.append(u)

    print(f"[DISCOVERY] total harvested usernames: {len(cleaned)}")
    return cleaned[:want]

    """
    Strategy:
      1) open tag pages derived from the keyword (split words into tags)
      2) collect /p/ links, open a few, harvest profile anchors
      3) fallback: search-like route (?q=) if tags failed
    """
    base_tokens = [t for t in re.split(r"[\s,/#]+", keyword.lower()) if len(t) >= 3][:4]
    tags = _unique(base_tokens)

    harvested: List[str] = []
    post_links: List[str] = []

    # gather post links from tags
    for tg in tags:
        ok = _open_tag_page(d, tg)
        if not ok: continue
        anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
        for a in anchors:
            href = a.get_attribute("href") or ""
            if "/p/" in href: post_links.append(href)
        post_links = _unique(post_links)
        if len(post_links) >= 24: break

    # fallback to /search?q=
    if not post_links:
        try:
            q = _u.quote(keyword)
            d.get(f"{BASE_URL.rstrip('/')}/search?q={q}")
            human_sleep(0.8, 1.1)
            anchors = d.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
            for a in anchors:
                href = a.get_attribute("href") or ""
                if "/p/" in href: post_links.append(href)
            post_links = _unique(post_links)
        except Exception:
            pass

    # open some posts and harvest usernames (owner/commenters/anchors)
    for href in post_links[:18]:
        try:
            d.get(href); human_sleep(0.6, 1.0)
            harvested += _collect_profile_usernames_on_page(d)
            if len(harvested) >= want: break
        except Exception:
            pass

    # filter
    cleaned = []
    for u in _unique(harvested):
        if already_followed(u): continue
        if u == SELF_USERNAME: continue
        if not re.match(r"^[a-z0-9._]{2,30}$", u): continue
        cleaned.append(u)
    return cleaned[:want]

# ----------------- orchestrators -----------------
def guard_logged_in(d) -> bool:
    if _looks_logged_in(d): return True
    _dismiss_common_modals(d)
    if _is_login_wall(d) and (LOGIN_USERNAME and LOGIN_PASSWORD):
        _try_programmatic_login(d)
        time.sleep(0.8)
        return _looks_logged_in(d)
    return _looks_logged_in(d)

def search_and_follow(keyword: str, batch_limit: int = 8, stop_evt=None):
    """
    Find candidate users for a keyword and follow up to `batch_limit`.
    - Blocks until we're truly logged in (cookie/UI) or times out.
    - Respects optional `stop_evt` (threading.Event) for the web UI.
    - Uses your existing discover_targets / follow_profile / human_sleep helpers.
    """
    import time, random

    done = skip = err = 0
    d = with_session()
    try:
        # --- hard login gate ---
        if not ensure_logged_in(d, 120):
            print("[LOGIN] manual login window... 60s")
            t0 = time.time()
            while time.time() - t0 < 60:
                if _looks_logged_in(d):
                    print("[LOGIN] manual login detected.")
                    break
                time.sleep(1)
            if not _looks_logged_in(d):
                print("[LOGIN] giving up; still not logged in.")
                try:
                    d.quit()
                except Exception:
                    pass
                return

        print(f"[RUN] keyword='{keyword}', batch_limit={batch_limit}")

        # --- discovery ---
        want = max(8, batch_limit * 12)  # generous buffer; filters will shrink it
        users = discover_targets(d, keyword, want=want)
        print(f"[DISCOVERY] produced {len(users)} usernames")

        if not users:
            print("[RUN] nothing to do.")
            return

        random.shuffle(users)

        # --- follow loop ---
        for u in users:
            # allow webapp STOP to interrupt immediately
            if stop_evt is not None and getattr(stop_evt, "is_set", lambda: False)():
                print("[RUN] stop requested -> exiting loop")
                break
            if done >= batch_limit:
                break
            if not u or u == SELF_USERNAME:
                skip += 1
                continue

            try:
                # follow_profile should handle private/size checks and pacing internally
                result = follow_profile(d, u)

                if result == "ok":
                    done += 1
                elif result == "skip":
                    skip += 1
                else:
                    err += 1
            except Exception as e:
                err += 1
                log_event("follow_err", u, str(e))

            # tiny extra jitter between accounts (your helpers add more human delay)
            human_sleep(0.2, 0.6)

        print(f"[RUN] done: ok={done}, skip={skip}, err={err}")

    finally:
        try:
            d.quit()
        except Exception:
            pass

    print(f"[RUN] keyword='{keyword}', batch_limit={batch_limit}")
    d = with_session()
    ok = skip = err = 0
    try:
        if not ensure_logged_in(d):
            print("[RUN] not logged in; nothing to do."); return
        users = discover_targets(d, keyword, want=batch_limit*12)

        if not users:
            print("[RUN] nothing to do."); return

        for u in users:
            if stop_evt and stop_evt.is_set():
                print("[STOP] requested â€” exiting run early"); break

            # follow with your existing quality gates (private/too_big/etc.)
            try:
                result = follow_profile(d, u)  # your existing function
                if result == "ok": ok += 1
                elif result == "skip": skip += 1
                else: err += 1
            except Exception:
                err += 1

            # light engagement burst (probabilistic)
            try:
                if random.random() < LIKE_BEFORE_FOLLOW_PROB and result == "ok":
                    like_recent_posts(d, how_many=random.randint(*LIKES_PER_PROFILE_RANGE))
            except Exception:
                pass

            if ok >= batch_limit:
                break

            human_idle()  # your existing jitter/sleep

    finally:
        print(f"[RUN] done: ok={ok}, skip={skip}, err={err}")
        try: d.quit()
        except: pass

    """
    Discover accounts around `keyword` and follow up to `batch_limit`.
    Ensures login first; prints detailed discovery logs.
    """
    print(f"[RUN] keyword='{keyword}', batch_limit={batch_limit}")
    d = with_session()
    success, skipped, errors = 0, 0, 0
    try:
        if not ensure_logged_in(d, wait_seconds=120):
            print("[RUN] aborted: not logged in.")
            return

        cands = discover_targets(d, keyword, want=max(40, batch_limit * 4))
        print(f"[DISCOVERY] produced {len(cands)} usernames")
        if not cands:
            print("[RUN] nothing to do.")
            return

        for u in cands:
            if success >= batch_limit:
                break
            ok, why = follow_profile(d, u, keyword=keyword)
            if ok:
                print("âœ“ follow", u); success += 1
            else:
                print(("Â· skip" if why.startswith(("already", "too_big", "private")) else "Ã— err"), u, why)
                if why.startswith(("already", "too_big", "private")): skipped += 1
                else: errors += 1
            human_sleep(0.8, 1.6)
    finally:
        try: d.quit()
        except: pass
    print(f"[RUN] done: ok={success}, skip={skipped}, err={errors}")

    """
    Discover accounts around `keyword` and follow up to `batch_limit`.
    Ensures login first; prints detailed discovery logs.
    """
    print(f"[RUN] keyword='{keyword}', batch_limit={batch_limit}")
    d = with_session()
    success, skipped, errors = 0, 0, 0
    try:
        ensure_logged_in(d)  # <â€” NEW: make sure session is logged in

        cands = discover_targets(d, keyword, want=max(40, batch_limit*4))
        print(f"[DISCOVERY] produced {len(cands)} usernames")
        if not cands:
            print("[RUN] nothing to do.")
            return

        for u in cands:
            if success >= batch_limit: break
            ok, why = follow_profile(d, u, keyword=keyword)
            if ok:
                print("âœ“ follow", u); success += 1
            else:
                print(("Â· skip" if why.startswith(("already","too_big","private")) else "Ã— err"), u, why)
                if why.startswith(("already","too_big","private")): skipped += 1
                else: errors += 1
            human_sleep(0.8, 1.6)
    finally:
        try: d.quit()
        except: pass
    print(f"[RUN] done: ok={success}, skip={skipped}, err={errors}")

    """
    Discover accounts around `keyword` and follow up to `batch_limit`.
    """
    print(f"[RUN] keyword='{keyword}', batch_limit={batch_limit}")
    d = with_session()
    success, skipped, errors = 0, 0, 0
    try:
        cands = discover_targets(d, keyword, want=max(40, batch_limit*4))
        print(f"[DISCOVERY] produced {len(cands)} usernames")
        if not cands:
            print("[RUN] nothing to do.")
            return

        for u in cands:
            if success >= batch_limit: break
            ok, why = follow_profile(d, u, keyword=keyword)
            if ok:
                print("âœ“ follow", u)
                success += 1
            else:
                print(("Â· skip" if why.startswith("already") or why.startswith("too_big") else "Ã— err"), u, why)
                if why.startswith("already") or why.startswith("too_big"): skipped += 1
                else: errors += 1
            human_sleep(0.8, 1.6)
    finally:
        try: d.quit()
        except: pass
    print(f"[RUN] done: ok={success}, skip={skipped}, err={errors}")

# ----------------- unfollow policy -----------------
def _unfollow_one(d, username: str) -> bool:
    """Open profile and unfollow; returns True on success."""
    d.get(_user_url(username)); human_sleep(0.5, 1.0)
    try:
        btn = d.find_element(
            By.XPATH,
            "//button[contains(.,'Following') or contains(.,'Requested') or @aria-pressed='true']"
        )
    except Exception:
        return False
    try: btn.click()
    except Exception:
        try: d.execute_script("arguments[0].click();", btn)
        except Exception: return False
    human_sleep(0.25, 0.5)
    for xp in (
        "//button[contains(.,'Unfollow')]",
        "//button[contains(.,'Remove')]",
        "//button[contains(.,'Cancel Request')]",
        "//button[contains(.,'Cancel')]",
    ):
        try:
            d.find_element(By.XPATH, xp).click()
            human_sleep(0.3, 0.7)
            return True
        except Exception:
            pass
    return False

def unfollow_due(batch_limit: int = 100):
    """
    Policy-based unfollow:
      - pulls users older than UNFOLLOW_AFTER_HOURS
      - randomizes order safely
      - respects QUIET_HOURS
    """
    from datetime import datetime
    # Quiet hours guard
    qstart, qend = QUIET_HOURS
    if qstart != qend:
        h = datetime.now().hour
        in_quiet = (qstart < qend and qstart <= h < qend) or (qstart > qend and (h >= qstart or h < qend))
        if in_quiet:
            print(f"[UNFOLLOW] inside quiet hours {qstart:02d}-{qend:02d} â€” skipping run.")
            return

    users = due_unfollows(UNFOLLOW_AFTER_HOURS, limit=batch_limit)
    if not users:
        print("[UNFOLLOW] nothing due.")
        return

    _rnd.shuffle(users)

    d = with_session()
    try:
        for u in users:
            ok = _unfollow_one(d, u)
            if ok:
                record_unfollow(u, "policy_due")
                print("âœ“ unfollow", u)
            else:
                log_event("unfollow_err", u, "click_fail")
                print("Ã— unfollow", u)
            human_sleep(0.5, 1.2)
    finally:
        try: d.quit()
        except: pass
# --- AUTO campaign runner (profile-mined keywords) ---
def run_auto_campaign(stop_evt=None, per_keyword: int = 6):
    """
    Builds keywords from the logged-in profile, then runs search_and_follow()
    for each keyword. stop_evt (threading.Event) is optional and checked
    between keywords so Stop in the web app is responsive.
    """
    d = with_session()
    kws = []
    try:
        if not ensure_logged_in(d):
            print("[AUTO] aborted: not logged in.")
            return
        kws = build_keywords_from_profile(d, max_terms=8)
        print(f"[AUTO] keywords â†’ {kws}")
    finally:
        try: d.quit()
        except: pass

    total_ok = total_skip = total_err = 0
    for kw in kws:
        if stop_evt and stop_evt.is_set():
            print("[AUTO] stop requested â€” exiting before next keyword.")
            break
        print(f"\n[AUTO] >>> {kw}")
        try:
            # reuse your main worker (one keyword per pass for smooth Stop)
            search_and_follow(kw, batch_limit=per_keyword)
        except Exception as e:
            print(f"[AUTO] error on '{kw}': {type(e).__name__}: {e}")
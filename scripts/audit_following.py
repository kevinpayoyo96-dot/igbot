# scripts/audit_following.py
import sys, time
sys.path.insert(0, r".\scripts")

from selenium.webdriver.common.by import By
from actions import with_session
from config import BASE_URL, SELF_USERNAME

def user_url(username: str) -> str:
    base = BASE_URL.rstrip("/")
    u = username.strip("/")
    return f"{base}/{u}/"

def following_urls(username: str):
    base = BASE_URL.rstrip("/")
    u = username.strip("/")
    # try the common routes your clone might support
    return [
        f"{base}/{u}/following/",
        f"{base}/{u}/following",
    ]

def open_following_view(d, username: str) -> bool:
    # 1) Go to profile
    d.get(user_url(username)); time.sleep(1.2)
    # 2) Try clicking a link that opens Following
    for xp in ("//a[contains(@href,'/following')]", "//a[.//div[contains(.,'Following')]]"):
        try:
            d.find_element(By.XPATH, xp).click()
            time.sleep(1.2)
            if in_following_view(d): return True
        except Exception:
            pass
    # 3) Try direct routes
    for url in following_urls(username):
        try:
            d.get(url); time.sleep(1.2)
            if in_following_view(d): return True
        except Exception:
            pass
    return False

def in_following_view(d) -> bool:
    # Accept either a modal or a dedicated page that obviously lists "Following"
    try:
        if d.find_elements(By.CSS_SELECTOR, "[role='dialog'], [role='listbox']"):
            return True
    except Exception:
        pass
    cu = (d.current_url or "").rstrip("/")
    return cu.endswith("/following")

def username_from_href(href: str):
    if not href: return None
    if "?" in href: href = href.split("?",1)[0]
    if "#" in href: href = href.split("#",1)[0]
    if href.startswith("http"):
        path = href.split("://",1)[1].split("/",1)[1] if "/" in href.split("://",1)[1] else ""
    else:
        path = href
    path = path.strip("/")
    # single-segment usernames only (exclude explore, terms, etc.)
    if not path or "/" in path: return None
    u = path
    # filter obvious non-user paths
    RESERVED = {"about", "privacy", "terms", "explore", "reels", "login", "accounts", "blog", "help", "inbox", "directory", "meta", "instagram", "www.instagram.com"}
    if u.lower() in RESERVED: return None
    return u

def collect_following_usernames(d, limit=50):
    # if there's a modal, scope to it; else use page
    scope = d
    try:
        scope = d.find_element(By.CSS_SELECTOR, "[role='dialog'], [role='listbox']")
    except Exception:
        pass
    seen, out = set(), []
    anchors = scope.find_elements(By.CSS_SELECTOR, "a[href^='/'], a[href^='https://']")
    for a in anchors:
        u = username_from_href(a.get_attribute("href") or "")
        if u and u not in seen:
            out.append(u); seen.add(u)
        if len(out) >= limit: break
    return out

if __name__ == "__main__":
    d = with_session()
    try:
        me = SELF_USERNAME.strip("/")
        if not me:
            print("ERROR: SELF_USERNAME is empty in config.py"); sys.exit(1)
        if not open_following_view(d, me):
            print("Could not open Following view (clone route differs).")
            sys.exit(2)
        users = collect_following_usernames(d, 50)
        print("Following in clone (first 50):", users)
    finally:
        try: d.quit()
        except Exception: pass

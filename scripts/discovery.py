# discovery.py
import re, time, random
from urllib.parse import urlparse, parse_qsl, unquote
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import BASE_URL, ALLOWED_HOSTS, ALLOWED_QUERY_KEYS, DISCOVERY_POSTS_TO_OPEN

USER_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
RESERVED = {
    "", "search", "explore", "reels", "direct", "stories", "p", "tv", "accounts",
    "login", "challenge", "privacy", "about", "terms", "help", "jobs", "api",
    "directory", "web", "emails", "lite", "meta", "ads", "channels", "blog"
}

# ------------ helpers
def _q_ok(qstr: str) -> bool:
    if not qstr: return True
    for k, _ in parse_qsl(qstr, keep_blank_values=True):
        if k not in ALLOWED_QUERY_KEYS:
            return False
    return True

def _username_from_href(href: str) -> str | None:
    if not href: return None
    if href.startswith("http"):
        pu = urlparse(href)
        if pu.netloc.lower() not in ALLOWED_HOSTS: return None
        if pu.fragment: return None
        if not _q_ok(pu.query): return None
        path = pu.path
    else:
        if "#" in href: return None
        path = href.split("?", 1)[0]
    path = unquote(path).strip("/")
    if not path: return None
    segs = path.split("/")
    if len(segs) != 1: return None
    u = segs[0]
    if u.lower() in RESERVED: return None
    if not USER_RE.match(u): return None
    return u

def _collect_usernames_anywhere(root) -> list[str]:
    names, seen = [], set()
    anchors = []
    anchors += root.find_elements(By.CSS_SELECTOR, "a[href^='/']")
    anchors += root.find_elements(By.CSS_SELECTOR, "a[href^='https://']")
    for a in anchors:
        href = a.get_attribute("href") or a.get_attribute("data-href") or ""
        u = _username_from_href(href)
        if u and u not in seen:
            names.append(u); seen.add(u)
            if len(names) >= 250: break
    return names

def _wait(driver, cond, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(cond)
    except Exception:
        return None

def _js_collect_post_links(driver) -> list[str]:
    """
    Return any URLs that look like /p/SHORTCODE/ from anchors OR data attributes.
    Works even if tiles are clickable divs without hrefs.
    """
    js = r"""
    const out = new Set();
    const want = s => (s && typeof s === "string" && s.includes("/p/"));
    document.querySelectorAll("a, [role=link], [role=button], [data-href], [data-nav], [data-uri]")
      .forEach(el => {
        const h = el.getAttribute && el.getAttribute("href");
        const d = el.dataset && (el.dataset.href || el.dataset.nav || el.dataset.uri);
        if (want(h)) out.add(h);
        if (want(d)) out.add(d);
      });
    return Array.from(out);
    """
    try:
        links = driver.execute_script(js) or []
        # normalize to absolute
        norm = []
        for href in links:
            if href.startswith("/"): norm.append(BASE_URL + href)
            elif href.startswith("http"): norm.append(href)
        # keep only /p/… paths
        norm = [u for u in norm if "/p/" in urlparse(u).path]
        # de-dup preserving order
        seen = set(); out = []
        for u in norm:
            if u not in seen:
                out.append(u); seen.add(u)
        return out
    except Exception:
        return []

def _open_keyword_results(driver, keyword: str):
    q = keyword.replace(" ", "+")
    driver.get(f"{BASE_URL}/explore/search/keyword/?q={q}")

def _harvest_from_post(driver) -> list[str]:
    # wait for post content; your dump showed Like controls on post pages
    _wait(driver, EC.presence_of_element_located((By.TAG_NAME, "article")), timeout=10)
    users = _collect_usernames_anywhere(driver)
    random.shuffle(users)
    return users[:60]

# ------------ public API
def discover_targets(driver, keyword, cap_users=80) -> list[str]:
    print(f"[DISCOVERY] keyword='{keyword}' → keyword-results page", flush=True)
    _open_keyword_results(driver, keyword)
    time.sleep(1.2)

    # Retry loop: scroll & re-scan for /p/ links (handles lazyload)
    post_links = []
    for i in range(6):
        links = _js_collect_post_links(driver)
        if links:
            post_links = links; break
        driver.execute_script("window.scrollBy(0, 1400);")
        time.sleep(0.8)
    print(f"[DISCOVERY] found post links: {len(post_links)}", flush=True)

    # If still nothing, try the home feed the same way
    if not post_links:
        print("[DISCOVERY] fallback → home feed", flush=True)
        driver.get(BASE_URL); time.sleep(1.2)
        for i in range(6):
            links = _js_collect_post_links(driver)
            if links:
                post_links = links; break
            driver.execute_script("window.scrollBy(0, 1400);")
            time.sleep(0.8)
        print(f"[DISCOVERY] home feed post links: {len(post_links)}", flush=True)

    # Open a handful of posts, harvest usernames
    harvested = []
    for href in post_links[:max(3, DISCOVERY_POSTS_TO_OPEN)]:
        try:
            print(f"[DISCOVERY] open post: {href}", flush=True)
            driver.get(href)
            time.sleep(0.8)
            users = _harvest_from_post(driver)
            print(f"[DISCOVERY] post harvested users: {len(users)}", flush=True)
            harvested.extend(users)
            # go back to results/home to continue
            driver.back()
            _wait(driver, EC.presence_of_element_located((By.TAG_NAME, "body")), timeout=6)
            time.sleep(0.4)
        except Exception as e:
            print(f"[DISCOVERY] post error: {e}", flush=True)

    # Merge & limit
    merged, seen = [], set()
    for u in harvested:
        if u not in seen:
            merged.append(u); seen.add(u)
        if len(merged) >= cap_users: break

    print(f"[DISCOVERY] total harvested usernames: {len(merged)}", flush=True)
    random.shuffle(merged)
    return merged

# Compatibility shim for older imports
def search_usernames(driver, keyword):
    return discover_targets(driver, keyword, cap_users=50)

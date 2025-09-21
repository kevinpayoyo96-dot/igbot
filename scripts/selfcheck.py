# selfcheck.py
import sys
from actions import with_session
from discovery import search_usernames
from selenium.webdriver.common.by import By

FOLLOW_SELECTORS = [
    "//button[contains(., 'Follow')]",
    "//button[@role='button' and contains(., 'Follow')]",
    "button[aria-label='Follow']",
    "button._acan._acap._acas",
    "button.follow-btn",
]

def has_follow_button(d):
    for sel in FOLLOW_SELECTORS:
        try:
            if sel.startswith("//"):
                if d.find_elements(By.XPATH, sel): return True
            else:
                if d.find_elements(By.CSS_SELECTOR, sel): return True
        except: pass
    return False

def open_profile(d, username, base_url):
    for pat in ("/{u}", "/{u}/", "/profile/{u}"):
        d.get(f"{base_url}{pat.format(u=username)}")
        if has_follow_button(d) or d.find_elements(By.TAG_NAME, "article"):
            return True
    return False

def main():
    kw = sys.argv[1] if len(sys.argv) > 1 else "cars"
    d = with_session()
    try:
        names = search_usernames(d, kw)
        print(f"[SELF-CHECK] Found {len(names)} candidate usernames for '{kw}'.")
        if not names:
            print("[FAIL] Search produced 0 usernames. Check search input/results selectors."); return
        probe = names[0]
        print(f"[SELF-CHECK] Probing first candidate: {probe}")
        from config import BASE_URL
        if not open_profile(d, probe, BASE_URL):
            print("[FAIL] Could not open a valid profile page for the first candidate.")
            return
        if not has_follow_button(d):
            print("[FAIL] Profile opened but no Follow button found (update selectors)."); return
        print("[PASS] Search dropdown, username extraction, profile open, and Follow button all good.")
    finally:
        try: d.quit()
        except: pass

if __name__ == "__main__":
    main()

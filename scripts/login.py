# login.py
import time, pickle
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import BASE_URL, COOKIES_PATH, AUTO_LOGIN, LOGIN_USERNAME, LOGIN_PASSWORD
from human import make_driver

def is_logged_in(d):
    try:
        # obvious “logged in” signals
        if d.find_elements(By.XPATH, "//a[contains(@href, '/accounts/edit') or contains(., 'Edit profile')]"):
            return True
        if d.find_elements(By.CSS_SELECTOR, "a[href*='/accounts/logout']"):
            return True
        # if login form visible, clearly not logged in
        if d.find_elements(By.NAME, "username") and d.find_elements(By.NAME, "password"):
            return False
    except Exception:
        pass
    return "login" not in (d.current_url or "").lower()

def auto_login(d) -> bool:
    if not AUTO_LOGIN or not LOGIN_USERNAME or not LOGIN_PASSWORD:
        return False
    try:
        d.get(f"{BASE_URL}/accounts/login/")
        WebDriverWait(d, 10).until(EC.presence_of_element_located((By.NAME, "username")))
        u = d.find_element(By.NAME, "username")
        p = d.find_element(By.NAME, "password")
        u.clear(); u.send_keys(LOGIN_USERNAME)
        p.clear(); p.send_keys(LOGIN_PASSWORD)
        # submit
        btns = d.find_elements(By.CSS_SELECTOR, "button[type='submit']")
        (btns[0] if btns else p).send_keys(Keys.ENTER)
        WebDriverWait(d, 20).until(EC.presence_of_element_located((By.TAG_NAME, "nav")))
        return is_logged_in(d)
    except Exception:
        return False

def manual_login(d, timeout=240) -> bool:
    print(f"Log in manually in this window. You have ~{timeout}s…")
    end = time.time() + timeout
    while time.time() < end:
        if is_logged_in(d):
            return True
        time.sleep(1.5)
    return False

def login_and_save_cookies():
    d = make_driver()
    d.get(BASE_URL)
    ok = is_logged_in(d)
    if not ok:
        ok = auto_login(d) or manual_login(d, timeout=240)
    if not ok:
        print("[LOGIN] Failed to detect login. Aborting.")
    else:
        pickle.dump(d.get_cookies(), open(COOKIES_PATH, "wb"))
        print(f"[LOGIN] Cookies saved → {COOKIES_PATH}")
    try: d.quit()
    except Exception: pass

if __name__ == "__main__":
    login_and_save_cookies()

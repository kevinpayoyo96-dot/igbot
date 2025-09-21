# utils.py
# -------------------
import os, random, time, pickle

def human_sleep(a=2.0, b=5.5):
    """Pause for a human-like random interval."""
    time.sleep(random.uniform(a, b))

def ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def save_cookies(driver, path):
    ensure_dir(path)
    with open(path, "wb") as f:
        pickle.dump(driver.get_cookies(), f)

def load_cookies(driver, path):
    if not os.path.exists(path):
        return False
    with open(path, "rb") as f:
        for c in pickle.load(f):
            driver.add_cookie(c)
    return True

def randomize_window(driver):
    driver.set_window_size(
        random.randint(1200, 1920),
        random.randint(700, 1080)
    )

def human_scroll(driver):
    for _ in range(random.randint(1,3)):
        driver.execute_script(f"window.scrollBy(0, {random.randint(200,700)});")
        human_sleep(0.7, 2.2)

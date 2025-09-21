# human.py
import random, time
from selenium.webdriver import ActionChains
import undetected_chromedriver as uc
from config import WINDOW_MODE, WINDOW_SIZE, WINDOW_POS

def human_sleep(a,b): time.sleep(random.uniform(a,b))

def human_scroll(driver):
    for _ in range(random.randint(1,3)):
        driver.execute_script(f"window.scrollBy(0,{random.randint(200,700)});")
        human_sleep(0.6,2.0)

def human_hover_click(driver, element):
    ac = ActionChains(driver)
    size = element.size
    xoff = int(size['width']*(0.4+random.random()*0.2))
    yoff = int(size['height']*(0.4+random.random()*0.2))
    ac.move_to_element_with_offset(element,xoff,yoff).pause(random.uniform(0.2,0.9)).click().perform()

def dwell(a,b): human_sleep(a,b)

def make_driver():
    opts = uc.ChromeOptions()
    if WINDOW_MODE.lower() == "headless":
        opts.add_argument("--headless=new")
    d = uc.Chrome(options=opts)
    try:
        mode = WINDOW_MODE.lower()
        if mode == "corner":
            w,h = WINDOW_SIZE; x,y = WINDOW_POS
            d.set_window_size(w, h); d.set_window_position(x, y)
        elif mode == "minimized":
            d.minimize_window()
    except Exception:
        pass
    return d

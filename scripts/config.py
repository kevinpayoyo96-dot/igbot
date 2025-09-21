# config.py
from urllib.parse import urlparse


# Your lab DNS maps this to the clone
BASE_URL = "https://www.instagram.com"

# Accept links from any of these hosts (handles www/no-www & your demo host if you keep it)
ALLOWED_HOSTS = {
    "www.instagram.com",
    "instagram.com",
    urlparse(BASE_URL).netloc.lower(),
    # "instagramdemo.kevinpayoyo.com",   # uncomment if your clone ever emits this host
}
# Allow profile links with these benign query keys (clone uses ?hl=…)
ALLOWED_QUERY_KEYS = {"hl"}   # e.g., /username/?hl=en
# Prefer UI-driven search (types in the search box and scrapes dropdown).
USE_UI_SEARCH_ONLY = False
# how many posts to open per keyword to harvest commenters
DISCOVERY_POSTS_TO_OPEN = 10

# Only used if USE_UI_SEARCH_ONLY = False
SEARCH_CANDIDATES = [
    "/explore/search/keyword/?q={q}",
    "/explore/people/?q={q}",
    "/explore/tags/{q}/",
    "/search?q={q}",
    "/",
]

PROFILE_CANDIDATES = [
    "/{u}",
    "/{u}/",
    "/profile/{u}",
]

SELF_USERNAME   = "sprvte.m4"          # optional: your own demo username to skip
SCORE_PATH      = "/bot-score"
COOKIES_PATH    = "./data/cookies.pkl"

# ---- Targeting rules ----
FOLLOWER_MAX = 10_000     # skip big accounts (> 1M followers)
FOLLOWER_MIN = 100

# ---- Pace & safety (1-week run) ----
MAX_FOLLOWS_PER_DAY   = 32
MAX_FOLLOWS_PER_HOUR  = 8
MAX_UNFOLLOWS_PER_HR  = 15
QUIET_HOURS = (1, 7)

# ---- Behavior tuning ----
MIN_DELAY_SEC = 3.5
MAX_DELAY_SEC = 12.0
SKIP_PROBABILITY  = 0.35
BROWSE_ONLY_PROB  = 0.30
LONG_IDLE_CHANCE  = 0.20
LONG_IDLE_RANGE   = (45.0, 150.0)
DWELL_RANGE_SEC   = (2.0, 6.0)

# ---- Follow → Unfollow cycle ----
UNFOLLOW_AFTER_HOURS     = 72
UNFOLLOW_RANDOM_JITTER_H = 9

# ---- Human extras ----
STORY_VIEW_PROB = 0.55
LIKE_POST_PROB  = 0.18

# how many items we sample during discovery
MAX_TAGS_PER_KEYWORD   = 3
MAX_POSTS_PER_TAG      = 6
MAX_USERS_PER_POST     = 30    # combined commenters + likers

# follow verification & private accounts
FOLLOW_VERIFY_MODE = "either"  # "either" | "button" | "list"
FOLLOW_PRIVATE_MODE = "skip"   # "skip" | "request"

LIKE_BEFORE_FOLLOW_PROB = 0.35   # 35% of profiles get 1–2 likes
LIKE_AFTER_FOLLOW_PROB  = 0.40     # ← add this
LIKES_PER_PROFILE_RANGE = (1, 2)
MAX_LIKES_PER_HOUR = 80
MAX_LIKES_PER_DAY  = 400

# --- UI / browser ---
HEADLESS = False      # True = no window, False = show window
WINDOW_MODE = "corner"          # "minimized" | "corner"
WINDOW_SIZE = (720, 820)   # used if not headless
WINDOW_POS  = (40, 40)      # used if not headless

# --- target quality / guards ---
FOLLOW_MAX_FOLLOWERS = 50000   # skip accounts above this follower count (None to disable)

# --- policy / scheduling ---
UNFOLLOW_AFTER_HOURS = 72
QUIET_HOURS = (0, 0)  # (start_hour, end_hour); identical values = disabled

# --- campaign tagging (helps filtering + unfollow-by-campaign) ---
CAMPAIGN = "trial_week"   # shown in DB 'note' for each follow; change per run if you want

# --- Optional automatic login ON THE CLONE ONLY ---
import os
LOGIN_USERNAME = os.getenv("IGCLONE_USER", "") or ""     # set via env or here
LOGIN_PASSWORD = os.getenv("IGCLONE_PASS", "") or ""     # set via env or here
AUTO_LOGIN = True                   # try programmatic login if creds exist
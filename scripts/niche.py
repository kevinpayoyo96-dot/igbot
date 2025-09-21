# scripts/niche.py  — dynamic niche builder
import re, time, json, random, math, collections
from pathlib import Path
from selenium.webdriver.common.by import By
from config import BASE_URL, SELF_USERNAME
# niche.py (add at top)
import unicodedata

def _norm(s: str) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\u200B-\u200F\uFEFF]", "", s)  # zero-width junk
    return s

# then use _norm() where we read text:
# header.text -> _norm(header.text)
# caption text -> _norm(scope.text)
# and in _tokenize():
def _tokenize(text):
    text = _norm(text)
    tags = [t.lower() for t in re.findall(r"#([A-Za-z0-9_]+)", text)]
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_]{%d,}" % (MIN_TOKEN_LEN-1,), text)]
    ...


KEYWORDS_PATH = Path("./data/keywords.json")
MIN_TOKEN_LEN = 3
DOC_MIN_DF = 2         # must appear in >= 2 different profiles/captions
MAX_TERMS   = 40
LOCATION_HINTS = ["toronto", "gta", "ontario", "canada"]  # tweakable

# Compact multi-language stopword set (en/es/fr/pt/de + platform words)
STOP = {
 "a","an","and","are","as","at","be","by","for","from","has","have","i","in","is","it","its",
 "la","el","los","las","de","del","y","o","un","una","con","para","por","que","en","lo",
 "le","les","des","du","et","ou","une","au","aux","sur","dans",
 "um","uma","dos","das","no","na","de","do","da","em","para",
 "der","die","das","und","oder","ein","eine","mit","auf","im",
 "the","to","of","on","us","we","you","me","my","our","your","they","them",
 "official","page","account","store","shop","free","new","best","love","life","about",
 "meta","instagram","thread","reels","blog","help","privacy","terms","login","api",
 "canada","toronto","gta","ontario",  # we’ll add these via LOCATION_HINTS deliberately
}

USER_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")

def _base(): return BASE_URL.rstrip("/")
def _uurl(u): return f"{_base()}/{u.strip('/')}/"

def _txt(x): return (x or "").replace("\n"," ").strip()

def _open_following(d, me):
    try:
        d.find_element(By.XPATH, "//a[contains(@href,'/following')]").click(); time.sleep(1.0); return True
    except Exception:
        d.get(f"{_uurl(me)}following/"); time.sleep(1.0); return True

def _collect_following_usernames(d, limit=150):
    seen, out = set(), []
    for a in d.find_elements(By.CSS_SELECTOR, "a[href^='/'], a[href^='https://']"):
        href = (a.get_attribute("href") or "").split("?",1)[0].split("#",1)[0]
        if not href: continue
        # must be same host and single-segment path => /username/
        if href.startswith("http"):
            try:
                host_path = href.split("://",1)[1]
                host, path = host_path.split("/",1) if "/" in host_path else (host_path, "")
                if host != _base().split("://",1)[1]: continue
            except Exception: continue
        else:
            path = href
        path = path.strip("/")
        if not path or "/" in path: continue
        if not USER_RE.match(path): continue
        if path not in seen:
            out.append(path); seen.add(path)
        if len(out) >= limit: break
    return out

def _open_recent_captions(d, how_many=2):
    caps = []
    tiles = d.find_elements(By.CSS_SELECTOR, "a, [role='link'], [role='button']")
    picked = []
    for el in tiles:
        try:
            if el.find_elements(By.TAG_NAME, "img"):
                picked.append(el)
                if len(picked)>=how_many: break
        except: pass
    for el in picked:
        try: d.execute_script("arguments[0].click();", el)
        except Exception:
            try: el.click()
            except Exception: continue
        time.sleep(0.6)
        scope = d
        try: scope = d.find_element(By.CSS_SELECTOR, "[role='dialog']")
        except: pass
        caps.append(_txt(scope.text))
        for sel in ("[aria-label='Close']", "button[aria-label*='Close']"):
            try: d.find_element(By.CSS_SELECTOR, sel).click(); break
            except: pass
        time.sleep(0.2)
    return caps

def _tokenize(text):
    # hashtags + words
    tags = [t.lower() for t in re.findall(r"#([A-Za-z0-9_]+)", text)]
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_]{%d,}" % (MIN_TOKEN_LEN-1,), text)]
    toks  = [t for t in tags + words if t not in STOP and not t.isdigit()]
    # split underscores and filter again
    out=[]
    for t in toks:
        for s in t.replace("_"," ").split():
            s=s.strip()
            if s and s not in STOP: out.append(s)
    return out

def _bigrams(tokens):
    return [f"{a} {b}" for a,b in zip(tokens, tokens[1:]) if a not in STOP and b not in STOP]

def build_keywords(driver, me=None, max_terms=MAX_TERMS):
    me = (me or SELF_USERNAME).strip("/")
    docs = []   # each doc = set(tokens) from one profile area or caption

    # self
    driver.get(_uurl(me)); time.sleep(0.8)
    try:
        header = driver.find_element(By.TAG_NAME, "header")
        docs.append(set(_tokenize(header.text)))
    except: pass
    docs += [set(_tokenize(c)) for c in _open_recent_captions(driver, how_many=3)]

    # following
    _open_following(driver, me)
    for u in _collect_following_usernames(driver, limit=120):
        driver.get(_uurl(u)); time.sleep(0.5)
        try:
            header = driver.find_element(By.TAG_NAME, "header")
            docs.append(set(_tokenize(header.text)))
        except: pass
        for cap in _open_recent_captions(driver, how_many=1):
            docs.append(set(_tokenize(cap)))

    # DF across docs (not raw frequency → filters junk like “otivational” typos)
    DF = collections.Counter()
    for s in docs:
        for t in s: DF[t]+=1

    # keep tokens that appear in >= DOC_MIN_DF docs
    keep = {t for t,c in DF.items() if c >= DOC_MIN_DF}

    # build scores (hashtags weigh more via crude prior)
    scores = collections.Counter()
    for s in docs:
        toks = [t for t in s if t in keep]
        bigs = _bigrams(sorted(toks))
        for t in toks: scores[t]+=1
        for b in bigs: scores[b]+=1  # phrases

    # rank and expand with locations
    ranked = [t for t,_ in scores.most_common(400)]
    result, seen = [], set()
    for t in ranked:
        if t in seen: continue
        result.append(t); seen.add(t)
        for loc in LOCATION_HINTS:
            result.append(f"{t} {loc}")
        if len(result) >= max_terms: break

    KEYWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEYWORDS_PATH.write_text(json.dumps({"built_at": time.time(), "keywords": result}, indent=2))
    return result

def load_keywords():
    if KEYWORDS_PATH.exists():
        try: return json.loads(KEYWORDS_PATH.read_text()).get("keywords", [])
        except: return []
    return []

def pick_keyword():
    kws = load_keywords()
    return random.choice(kws) if kws else None

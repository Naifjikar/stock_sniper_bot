import os, time, re, sqlite3, hashlib, logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import requests

# =========================
# ENV
# =========================
TG_TOKEN = (os.getenv("TG_TOKEN") or "").strip()
TG_CHAT_ID = (os.getenv("TG_CHAT_ID") or "").strip()
MASSIVE_API_KEY = re.sub(r"[^\x20-\x7E]", "", (os.getenv("MASSIVE_API_KEY") or "")).strip()

def req(name, val):
    if not val:
        raise RuntimeError(f"Missing ENV var: {name}")

req("TG_TOKEN", TG_TOKEN)
req("TG_CHAT_ID", TG_CHAT_ID)
req("MASSIVE_API_KEY", MASSIVE_API_KEY)

# =========================
# SETTINGS
# =========================
RIYADH_TZ = ZoneInfo("Asia/Riyadh")
RUN_START_HOUR = 12
RUN_END_HOUR = 24
BLOCK_WEEKEND = True

PRICE_MIN = 0.01
PRICE_MAX = 15.0

# زخم
MOMENTUM_PCT = 10.0
MIN_DAY_VOLUME = 300_000
MAX_MOMENTUM_PER_DAY = 5

# أخبار
MAX_NEWS_PER_DAY = 6
NEWS_LOOKBACK_MIN = 90

POLL_SECONDS = 45
SLEEP_BETWEEN_CALLS = 0.25

API_BASE = "https://api.massive.com"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# =========================
# DB
# =========================
con = sqlite3.connect("public_seen.db")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS seen (k TEXT PRIMARY KEY, ts INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS daily (d TEXT PRIMARY KEY, mom INTEGER, news INTEGER)")
con.commit()

def now_riyadh():
    return datetime.now(RIYADH_TZ)

def today_key():
    return now_riyadh().date().isoformat()

def is_weekend():
    return now_riyadh().weekday() >= 5

def in_run_window():
    h = now_riyadh().hour
    return RUN_START_HOUR <= h < RUN_END_HOUR

def get_counts():
    cur.execute("SELECT mom, news FROM daily WHERE d=?", (today_key(),))
    r = cur.fetchone()
    return (r[0], r[1]) if r else (0, 0)

def inc_mom():
    m, n = get_counts()
    cur.execute("INSERT OR REPLACE INTO daily VALUES (?,?,?)", (today_key(), m+1, n))
    con.commit()

def inc_news():
    m, n = get_counts()
    cur.execute("INSERT OR REPLACE INTO daily VALUES (?,?,?)", (today_key(), m, n+1))
    con.commit()

def seen(k):
    cur.execute("SELECT 1 FROM seen WHERE k=?", (k,))
    return cur.fetchone() is not None

def mark(k):
    cur.execute("INSERT OR REPLACE INTO seen VALUES (?,?)", (k, int(time.time())))
    con.commit()

# =========================
# Telegram
# =========================
def tg_send(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 429:
            time.sleep(5)
            return tg_send(text)
    except Exception as e:
        logging.error(e)

# =========================
# API
# =========================
def api(path, params=None):
    r = requests.get(
        f"{API_BASE}{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {MASSIVE_API_KEY}"},
        timeout=20
    )
    if r.status_code == 429:
        time.sleep(1)
        return api(path, params)
    r.raise_for_status()
    return r.json()

def r2(x): 
    return round(float(x), 2)

# =========================
# NEWS FILTER
# =========================
IMPORTANT_KW = [
    "acquisition","merger","partnership","agreement",
    "launch","product","fda","approval",
    "contract","award","earnings","guidance"
]

def important_news(txt):
    t = txt.lower()
    return any(k in t for k in IMPORTANT_KW)

def translate_ar(title):
    return f"الشركة تعلن عن {title}"

# =========================
# MAIN
# =========================
def main():
    tg_send("✅ بوت القناة العامة شغال (أخبار + زخم)")
    while True:
        try:
            if BLOCK_WEEKEND and is_weekend():
                time.sleep(POLL_SECONDS); continue
            if not in_run_window():
                time.sleep(POLL_SECONDS); continue

            mom_c, news_c = get_counts()

            # زخم
            if mom_c < MAX_MOMENTUM_PER_DAY:
                data = api("/v2/snapshot/locale/us/markets/stocks/gainers")
                for t in data.get("tickers", [])[:40]:
                    sym = t.get("ticker")
                    day = t.get("day") or {}
                    prev = t.get("prevDay") or {}
                    price = float(day.get("c") or 0)
                    vol = float(day.get("v") or 0)
                    prev_c = float(prev.get("c") or 0)
                    if not sym or not (PRICE_MIN <= price <= PRICE_MAX):
                        continue
                    if vol < MIN_DAY_VOLUME or prev_c <= 0:
                        continue
                    chg = (price - prev_c) / prev_c * 100
                    if chg < MOMENTUM_PCT:
                        continue

                    k = hashlib.sha1(f"{today_key()}|MOM|{sym}".encode()).hexdigest()
                    if seen(k):
                        continue

                    tg_send(
                        f"🚨 Momentum Alert\n\n"
                        f"${sym}\n"
                        f"Price now: {r2(price)}"
                    )
                    mark(k); inc_mom()
                    time.sleep(3)
                    break

            # أخبار
            if news_c < MAX_NEWS_PER_DAY:
                news = api("/v2/reference/news", {
                    "limit": 50,
                    "order": "desc",
                    "sort": "published_utc"
                }).get("results", [])

                for n in news:
                    title = n.get("title","")
                    if not title or not important_news(title):
                        continue
                    tickers = n.get("tickers") or []
                    if not tickers:
                        continue
                    sym = tickers[0]

                    k = hashlib.sha1(f"{today_key()}|NEWS|{sym}|{title}".encode()).hexdigest()
                    if seen(k):
                        continue

                    tg_send(
                        f"📰 Breaking News\n\n"
                        f"${sym}\n"
                        f"{title}\n\n"
                        f"———\n\n"
                        f"📰 خبر عاجل\n\n"
                        f"${sym}\n"
                        f"{translate_ar(title)}"
                    )
                    mark(k); inc_news()
                    time.sleep(3)
                    break

        except Exception as e:
            logging.exception(e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()

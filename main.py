import os, time, json, hashlib, sqlite3, logging
from datetime import datetime, timezone, date, timedelta
import requests

# ===== ENV =====
TG_TOKEN = (os.getenv("TG_TOKEN") or "").strip()
TG_CHAT_ID = (os.getenv("TG_CHAT_ID") or "").strip()
MASSIVE_API_KEY = (os.getenv("MASSIVE_API_KEY") or "").strip()

def req(name, val):
    if not val:
        raise RuntimeError(f"Missing ENV var: {name}")

req("TG_TOKEN", TG_TOKEN)
req("TG_CHAT_ID", TG_CHAT_ID)
req("MASSIVE_API_KEY", MASSIVE_API_KEY)

# ===== SETTINGS =====
PRICE_MIN = 1.0
PRICE_MAX = 10.0

MIN_DAY_CHANGE_PCT = 10.0     # زخم
MIN_DAY_VOLUME = 300_000      # طلبك

POLL_SECONDS = 60
CANDLE_RES_MIN = 3
LOOKBACK_BARS = 200

STOP_PCT = 0.09
TARGET_PCTS = [0.08, 0.15, 0.25, 0.40]

MAX_SIGNALS_PER_DAY = 5

SLEEP_BETWEEN_CALLS = 0.2

# اختر واحد:
API_BASE = "https://api.massive.com"   # الرسمي الجديد
# API_BASE = "https://api.polygon.io"  # شغال برضو

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ===== DB =====
con = sqlite3.connect("seen.db")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS seen (k TEXT PRIMARY KEY, ts INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS daily (d TEXT PRIMARY KEY, n INTEGER)")
con.commit()

def today_key() -> str:
    return date.today().isoformat()

def get_today_count() -> int:
    d = today_key()
    cur.execute("SELECT n FROM daily WHERE d=?", (d,))
    row = cur.fetchone()
    return int(row[0]) if row else 0

def inc_today_count():
    d = today_key()
    n = get_today_count() + 1
    cur.execute("INSERT OR REPLACE INTO daily (d, n) VALUES (?, ?)", (d, n))
    con.commit()

def seen_before(key: str) -> bool:
    cur.execute("SELECT 1 FROM seen WHERE k=?", (key,))
    return cur.fetchone() is not None

def mark_seen(key: str):
    cur.execute("INSERT OR REPLACE INTO seen (k, ts) VALUES (?,?)", (key, int(time.time())))
    con.commit()

# ===== Telegram =====
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 429:
            try:
                wait = r.json().get("parameters", {}).get("retry_after", 5)
            except Exception:
                wait = 5
            time.sleep(wait + 1)
            return tg_send(text)
        if not r.ok:
            logging.error("TG ERROR %s %s", r.status_code, r.text)
    except Exception as e:
        logging.error("TG SEND FAILED: %s", e)

# ===== Massive/Polygon =====
def massive_get(path: str, params: dict | None = None):
    params = dict(params or {})
    params["apiKey"] = MASSIVE_API_KEY
    url = f"{API_BASE}{path}"
    r = requests.get(url, params=params, timeout=25)
    if r.status_code == 429:
        time.sleep(1.2)
        return massive_get(path, params)
    r.raise_for_status()
    return r.json()

def get_top_gainers(limit: int = 20) -> list[dict]:
    """
    Top market movers (gainers). Endpoint returns top 20 by default.
    """
    data = massive_get("/v2/snapshot/locale/us/markets/stocks/gainers", {})
    # Structure usually has "tickers": [...]
    tickers = data.get("tickers") or []
    return tickers[:limit]

def get_aggs_3m(symbol: str):
    """
    3-min aggregates for LOOKBACK_BARS
    Polygon/Massive aggs use timestamps; safest to use millisecond epoch.
    """
    now = datetime.now(timezone.utc)
    frm = now - timedelta(minutes=CANDLE_RES_MIN * LOOKBACK_BARS)
    # Polygon expects YYYY-MM-DD or millisecond epoch in path; epoch-ms is reliable
    to_ms = int(now.timestamp() * 1000)
    from_ms = int(frm.timestamp() * 1000)

    path = f"/v2/aggs/ticker/{symbol}/range/{CANDLE_RES_MIN}/minute/{from_ms}/{to_ms}"
    # limit helps, adjusted=false keeps raw
    data = massive_get(path, {"adjusted": "false", "sort": "asc", "limit": 50000})
    results = data.get("results") or []
    if not results:
        return None
    return results

def pivot_highs(highs, left=2, right=2):
    pivots = []
    for i in range(left, len(highs) - right):
        h = highs[i]
        if all(h > highs[i - j] for j in range(1, left + 1)) and all(h >= highs[i + j] for j in range(1, right + 1)):
            pivots.append(h)
    return pivots

def nearest_resistance_from_aggs(aggs, last_price: float) -> float | None:
    highs = [float(a.get("h", 0) or 0) for a in aggs]
    highs = [h for h in highs if h > 0]
    if not highs:
        return None
    pivs = pivot_highs(highs, 2, 2)
    above = sorted([p for p in pivs if p > last_price])
    if above:
        return float(above[0])
    tail = highs[-50:] if len(highs) >= 50 else highs
    return float(max(tail)) if tail else None

def build_levels(entry: float):
    stop = round(entry * (1 - STOP_PCT), 4)
    targets = [round(entry * (1 + p), 4) for p in TARGET_PCTS]
    return stop, targets

def snapshot_fields(t: dict):
    """
    Normalize fields from snapshot ticker item.
    Common fields:
      - ticker: "AAPL"
      - day: { o,h,l,c,v }
      - prevDay: { c }
      - todaysChangePerc (or similar)
      - lastTrade / lastQuote etc (optional)
    """
    sym = (t.get("ticker") or "").strip().upper()
    day = t.get("day") or {}
    prev = t.get("prevDay") or {}

    last_price = float(day.get("c") or 0)
    day_vol = float(day.get("v") or 0)
    prev_close = float(prev.get("c") or 0)

    # polygon often includes todaysChangePerc
    chg_pct = t.get("todaysChangePerc")
    if chg_pct is None and last_price > 0 and prev_close > 0:
        chg_pct = (last_price - prev_close) / prev_close * 100.0

    try:
        chg_pct = float(chg_pct or 0)
    except Exception:
        chg_pct = 0.0

    return sym, last_price, prev_close, chg_pct, day_vol

def main_loop():
    tg_send("✅ بوت الزخم شغال (Massive/Polygon - بدون أخبار)")

    while True:
        try:
            sent = get_today_count()
            logging.info("Heartbeat... daily_sent=%s", sent)

            if sent >= MAX_SIGNALS_PER_DAY:
                time.sleep(POLL_SECONDS)
                continue

            gainers = get_top_gainers(limit=20)

            for t in gainers:
                if get_today_count() >= MAX_SIGNALS_PER_DAY:
                    break

                sym, last_price, prev_close, chg_pct, day_vol = snapshot_fields(t)
                if not sym or last_price <= 0:
                    continue

                # Dedup per symbol/day
                day = today_key()
                k = hashlib.sha1(f"{day}|{sym}".encode("utf-8")).hexdigest()
                if seen_before(k):
                    continue

                # filters
                if not (PRICE_MIN <= last_price <= PRICE_MAX):
                    mark_seen(k)
                    continue
                if chg_pct < MIN_DAY_CHANGE_PCT:
                    mark_seen(k)
                    continue
                if day_vol < MIN_DAY_VOLUME:
                    mark_seen(k)
                    continue

                aggs = get_aggs_3m(sym)
                time.sleep(SLEEP_BETWEEN_CALLS)
                if not aggs:
                    mark_seen(k)
                    continue

                res = nearest_resistance_from_aggs(aggs, last_price)
                if not res:
                    mark_seen(k)
                    continue

                entry = round(res, 4)
                stop, targets = build_levels(entry)

                msg = (
                    f"{sym}\n"
                    f"دخول {entry}\n"
                    f"وقف {stop}\n"
                    f"اهداف {targets[0]} - {targets[1]} - {targets[2]} - {targets[3]}\n"
                    f"زخم: {chg_pct:.2f}% | فوليوم: {int(day_vol):,} | سعر: {last_price:.2f}"
                )

                tg_send(msg)
                mark_seen(k)
                inc_today_count()
                time.sleep(2)

        except Exception as e:
            logging.exception(e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main_loop()

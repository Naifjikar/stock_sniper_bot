import os, time, hashlib, sqlite3, logging
from datetime import datetime, timezone, date
import requests

# ===== ENV =====
TG_TOKEN = (os.getenv("TG_TOKEN") or "").strip()
TG_CHAT_ID = (os.getenv("TG_CHAT_ID") or "").strip()

POLYGON_API_KEY = (os.getenv("POLYGON_API_KEY") or "").strip()
FINNHUB_API_KEY = (os.getenv("FINNHUB_API_KEY") or "").strip()

# ===== SETTINGS =====
PRICE_MIN = 1.0
PRICE_MAX = 10.0

MIN_DAY_VOLUME = 300_000     # ✅ طلبك
MIN_DAY_CHANGE_PCT = 10.0    # زخم حقيقي

POLL_SECONDS = 60            # كل دقيقة
CANDLE_RES_MIN = 3           # 3 minutes
LOOKBACK_BARS = 200

STOP_PCT = 0.09              # -9%
TARGET_PCTS = [0.08, 0.15, 0.25, 0.40]  # +8% +15% +25% +40%

MAX_SIGNALS_PER_DAY = 5      # تقدر تخليها 999 لو تبي “مفتوح”

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def req(name, val):
    if not val:
        raise RuntimeError(f"Missing ENV var: {name}")

req("TG_TOKEN", TG_TOKEN)
req("TG_CHAT_ID", TG_CHAT_ID)
req("POLYGON_API_KEY", POLYGON_API_KEY)
req("FINNHUB_API_KEY", FINNHUB_API_KEY)

# ===== DB (dedup + daily limit) =====
con = sqlite3.connect("seen.db")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS seen (k TEXT PRIMARY KEY, ts INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS daily (d TEXT PRIMARY KEY, n INTEGER)")
con.commit()

def seen_before(key: str) -> bool:
    cur.execute("SELECT 1 FROM seen WHERE k=?", (key,))
    return cur.fetchone() is not None

def mark_seen(key: str):
    cur.execute("INSERT OR REPLACE INTO seen (k, ts) VALUES (?,?)", (key, int(time.time())))
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

# ===== Telegram =====
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "disable_web_page_preview": True}
    r = requests.post(url, json=payload, timeout=20)

    # Rate limit handling
    if r.status_code == 429:
        try:
            wait = r.json().get("parameters", {}).get("retry_after", 5)
        except Exception:
            wait = 5
        time.sleep(wait + 1)
        return tg_send(text)

    # Don't crash the bot; log the reason
    if not r.ok:
        logging.error("TG ERROR %s %s", r.status_code, r.text)
        return

# ===== Polygon helpers (Scanner) =====
def polygon_get(path: str, params: dict | None = None):
    params = dict(params or {})
    params["apiKey"] = POLYGON_API_KEY
    url = f"https://api.polygon.io/{path}"
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_momentum_candidates(limit: int = 50):
    """
    Uses Polygon snapshot gainers to get real-time momentum candidates.
    We filter later by price/volume/change.
    """
    data = polygon_get("v2/snapshot/locale/us/markets/stocks/gainers", {"limit": limit})
    tickers = data.get("tickers") or []
    return tickers

def extract_metrics_from_polygon(t) -> tuple[str, float, float, float] | None:
    """
    Returns: (symbol, last_price, day_volume, day_change_pct)
    """
    sym = (t.get("ticker") or "").strip()
    if not sym:
        return None

    # last price
    last = None
    if t.get("lastTrade") and isinstance(t["lastTrade"], dict):
        last = t["lastTrade"].get("p")
    if not last and t.get("min") and isinstance(t["min"], dict):
        last = t["min"].get("c")
    if not last and t.get("day") and isinstance(t["day"], dict):
        last = t["day"].get("c")

    # day volume
    day_v = None
    if t.get("day") and isinstance(t["day"], dict):
        day_v = t["day"].get("v")

    # day change %
    chg_pct = None
    if t.get("todaysChangePerc") is not None:
        chg_pct = float(t["todaysChangePerc"])
    elif t.get("todaysChangePerc") is None and t.get("todaysChange") is not None:
        # fallback if percent missing (rare)
        pass

    try:
        last = float(last) if last is not None else None
        day_v = float(day_v) if day_v is not None else 0.0
        chg_pct = float(chg_pct) if chg_pct is not None else None
    except Exception:
        return None

    if last is None or chg_pct is None:
        return None

    return sym, last, day_v, chg_pct

# ===== Finnhub helpers (3m candles for resistance) =====
def finnhub_get(path: str, params: dict):
    params = dict(params)
    params["token"] = FINNHUB_API_KEY
    url = f"https://finnhub.io/api/v1/{path}"
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def get_candles_3m(symbol: str):
    now = int(time.time())
    frm = now - (CANDLE_RES_MIN * 60 * LOOKBACK_BARS)
    data = finnhub_get("stock/candle", {
        "symbol": symbol,
        "resolution": str(CANDLE_RES_MIN),
        "from": frm,
        "to": now
    })
    if data.get("s") != "ok":
        return None
    return data

def pivot_highs(highs, left=2, right=2):
    pivots = []
    for i in range(left, len(highs) - right):
        h = highs[i]
        if all(h > highs[i - j] for j in range(1, left + 1)) and all(h >= highs[i + j] for j in range(1, right + 1)):
            pivots.append(h)
    return pivots

def nearest_resistance(symbol: str, last_price: float) -> float | None:
    candles = get_candles_3m(symbol)
    if not candles:
        return None
    highs = candles["h"]
    pivs = pivot_highs(highs, 2, 2)
    above = sorted([p for p in pivs if p > last_price])
    if above:
        return float(above[0])
    # fallback: recent max high
    if len(highs) >= 50:
        return float(max(highs[-50:]))
    return float(max(highs)) if highs else None

def build_levels(entry: float):
    stop = round(entry * (1 - STOP_PCT), 4)
    targets = [round(entry * (1 + p), 4) for p in TARGET_PCTS]
    return stop, targets

def main_loop():
    # startup message (won't crash if Telegram fails)
    try:
        tg_send("✅ بوت الزخم شغال (بدون أخبار)")
    except Exception:
        pass

    while True:
        try:
            logging.info("Heartbeat... daily_sent=%s", get_today_count())

            # Stop if daily limit reached
            if get_today_count() >= MAX_SIGNALS_PER_DAY:
                logging.info("Daily limit reached (%s). Sleeping...", MAX_SIGNALS_PER_DAY)
                time.sleep(POLL_SECONDS)
                continue

            candidates = fetch_momentum_candidates(limit=60)

            for t in candidates:
                m = extract_metrics_from_polygon(t)
                if not m:
                    continue
                sym, last_price, day_vol, chg_pct = m

                # Filters
                if not (PRICE_MIN <= last_price <= PRICE_MAX):
                    continue
                if day_vol < MIN_DAY_VOLUME:
                    continue
                if chg_pct < MIN_DAY_CHANGE_PCT:
                    continue

                # Dedup per symbol + day (so it doesn't spam same ticker)
                day = today_key()
                dedup_key = hashlib.sha1(f"{day}|{sym}".encode("utf-8")).hexdigest()
                if seen_before(dedup_key):
                    continue

                res = nearest_resistance(sym, last_price)
                if not res:
                    mark_seen(dedup_key)
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
                mark_seen(dedup_key)
                inc_today_count()

                # stop if reached limit
                if get_today_count() >= MAX_SIGNALS_PER_DAY:
                    break

                time.sleep(2)

        except Exception as e:
            logging.exception(e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main_loop()

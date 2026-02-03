import os, time, re, hashlib, sqlite3, logging
from datetime import datetime, timezone
import requests

# ===== ENV =====
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

PRICE_MIN = 1.0
PRICE_MAX = 10.0
POLL_SECONDS = 60
CANDLE_RES_MIN = 3  # 3 minutes
LOOKBACK_BARS = 200

# Targets in "add to entry" dollars (as you requested)
TARGETS_ADD = [0.08, 0.15, 0.25, 0.40]  # when entry = 1.00; we’ll scale by entry (percent-like)
STOP_PCT = 0.09  # -9%

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def req(name, val):
    if not val:
        raise RuntimeError(f"Missing ENV var: {name}")

req("TG_TOKEN", TG_TOKEN)
req("TG_CHAT_ID", TG_CHAT_ID)
req("FINNHUB_API_KEY", FINNHUB_API_KEY)

# ===== DB (dedup) =====
con = sqlite3.connect("seen.db")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS seen (k TEXT PRIMARY KEY, ts INTEGER)")
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
    r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=20)
    if r.status_code == 429:
        try:
            wait = r.json().get("parameters", {}).get("retry_after", 5)
        except Exception:
            wait = 5
        time.sleep(wait + 1)
        return tg_send(text)
    r.raise_for_status()

# ===== Finnhub helpers =====
def finnhub_get(path: str, params: dict):
    params = dict(params)
    params["token"] = FINNHUB_API_KEY
    url = f"https://finnhub.io/api/v1/{path}"
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def get_last_price(symbol: str) -> float | None:
    try:
        q = finnhub_get("quote", {"symbol": symbol})
        return float(q.get("c") or 0) or None
    except Exception:
        return None

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
    # arrays: c,h,l,t,o,v
    return data

def pivot_highs(highs, left=2, right=2):
    pivots = []
    for i in range(left, len(highs)-right):
        h = highs[i]
        if all(h > highs[i-j] for j in range(1, left+1)) and all(h >= highs[i+j] for j in range(1, right+1)):
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
        return above[0]
    # fallback: recent max high
    return max(highs[-50:]) if len(highs) >= 50 else max(highs)

def build_levels(entry: float):
    stop = round(entry * (1 - STOP_PCT), 4)
    # Your “8/15/25/40” logic: treat as +8% +15% +25% +40% of entry
    t1 = round(entry * (1 + 0.08), 4)
    t2 = round(entry * (1 + 0.15), 4)
    t3 = round(entry * (1 + 0.25), 4)
    t4 = round(entry * (1 + 0.40), 4)
    return stop, [t1, t2, t3, t4]

# ===== News: Finnhub market news =====
def fetch_news():
    # general market news; we’ll try to extract tickers from related field when possible
    # You can later switch to company-news endpoints if you want.
    items = finnhub_get("news", {"category": "general"})
    return items[:30] if isinstance(items, list) else []

def extract_tickers_from_text(text: str):
    # quick fallback if no tickers; uppercase 2-5 letters
    return list(set(re.findall(r"\b[A-Z]{2,5}\b", text)))[:5]

def main_loop():
    tg_send("✅ بوت الأسهم شغال (MVP خبر + تحليل)")

    while True:
        try:
            logging.info("Heartbeat...")
            news_items = fetch_news()

            for it in news_items:
                title = (it.get("headline") or "").strip()
                link = (it.get("url") or "").strip()
                ts = int(it.get("datetime") or 0)
                key = hashlib.sha1(f"{title}|{link}|{ts}".encode("utf-8")).hexdigest()

                if not title or seen_before(key):
                    continue

                # Try get tickers from Finnhub if present, else parse title
                tickers = it.get("related")
                symbols = []
                if tickers:
                    symbols = [s.strip() for s in tickers.split(",") if s.strip()]
                else:
                    symbols = extract_tickers_from_text(title)

                # filter & pick first valid symbol in price range
                picked = None
                last_price = None
                for sym in symbols:
                    lp = get_last_price(sym)
                    if lp and PRICE_MIN <= lp <= PRICE_MAX:
                        picked = sym
                        last_price = lp
                        break

                if not picked:
                    mark_seen(key)
                    continue

                res = nearest_resistance(picked, last_price)
                if not res:
                    mark_seen(key)
                    continue

                entry = round(res, 4)
                stop, targets = build_levels(entry)

                msg = (
                    f"{picked}\n"
                    f"دخول {entry}\n"
                    f"وقف {stop}\n"
                    f"اهداف {targets[0]} - {targets[1]} - {targets[2]} - {targets[3]}\n"
                    f"خبر: {title}"
                )

                tg_send(msg)
                mark_seen(key)
                time.sleep(2)  # avoid spam

        except Exception as e:
            logging.exception(e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main_loop()

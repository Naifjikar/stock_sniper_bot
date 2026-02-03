import os, time, json, hashlib, sqlite3, logging
from datetime import date
import requests

# ===== ENV =====
TG_TOKEN = (os.getenv("TG_TOKEN") or "").strip()
TG_CHAT_ID = (os.getenv("TG_CHAT_ID") or "").strip()
FINNHUB_API_KEY = (os.getenv("FINNHUB_API_KEY") or "").strip()

def req(name, val):
    if not val:
        raise RuntimeError(f"Missing ENV var: {name}")

req("TG_TOKEN", TG_TOKEN)
req("TG_CHAT_ID", TG_CHAT_ID)
req("FINNHUB_API_KEY", FINNHUB_API_KEY)

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

# عدد الأسهم اللي نمسحها كل دورة (مهم عشان حدود Finnhub)
BATCH_SIZE = 25   # 25 سهم/دقيقة تقريباً (مناسب للحدود)
SLEEP_BETWEEN_CALLS = 0.2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ===== DB =====
con = sqlite3.connect("seen.db")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS seen (k TEXT PRIMARY KEY, ts INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS daily (d TEXT PRIMARY KEY, n INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS cursor (k TEXT PRIMARY KEY, v INTEGER)")
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

def get_cursor() -> int:
    cur.execute("SELECT v FROM cursor WHERE k='i'")
    row = cur.fetchone()
    return int(row[0]) if row else 0

def set_cursor(v: int):
    cur.execute("INSERT OR REPLACE INTO cursor (k, v) VALUES ('i', ?)", (int(v),))
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

# ===== Finnhub =====
def finnhub_get(path: str, params: dict):
    params = dict(params)
    params["token"] = FINNHUB_API_KEY
    url = f"https://finnhub.io/api/v1/{path}"
    r = requests.get(url, params=params, timeout=20)
    if r.status_code == 429:
        time.sleep(1.2)
        return finnhub_get(path, params)
    r.raise_for_status()
    return r.json()

def load_universe() -> list[str]:
    """
    نحمل قائمة الأسهم مرة وحدة ونحفظها في ملف لتسريع التشغيل.
    """
    cache_file = "symbols.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                syms = json.load(f)
            if isinstance(syms, list) and len(syms) > 1000:
                return syms
        except Exception:
            pass

    # Finnhub symbol list
    # بعض الحسابات تنجح مع exchange=US، لو ما نجحت نجرب NASDAQ/NYSE/AMEX
    exchanges = ["US", "NASDAQ", "NYSE", "AMEX"]
    all_syms = []

    for ex in exchanges:
        try:
            rows = finnhub_get("stock/symbol", {"exchange": ex})
            if isinstance(rows, list) and rows:
                for it in rows:
                    s = (it.get("symbol") or "").strip().upper()
                    # فلترة رموز نظيفة (بدون . وبدون -)
                    if 1 <= len(s) <= 5 and s.isalpha():
                        all_syms.append(s)
                if len(all_syms) > 2000:
                    break
        except Exception as e:
            logging.warning("Universe fetch failed for %s: %s", ex, e)

    # إزالة تكرارات
    syms = sorted(list(set(all_syms)))

    with open(cache_file, "w") as f:
        json.dump(syms, f)

    return syms

def get_quote(symbol: str) -> tuple[float, float, float] | None:
    """
    returns: (current_price, prev_close, change_pct)
    """
    try:
        q = finnhub_get("quote", {"symbol": symbol})
        c = float(q.get("c") or 0)
        pc = float(q.get("pc") or 0)
        if c <= 0 or pc <= 0:
            return None
        chg_pct = (c - pc) / pc * 100.0
        return c, pc, chg_pct
    except Exception:
        return None

def get_candles_3m(symbol: str):
    now = int(time.time())
    frm = now - (CANDLE_RES_MIN * 60 * LOOKBACK_BARS)
    try:
        data = finnhub_get("stock/candle", {
            "symbol": symbol,
            "resolution": str(CANDLE_RES_MIN),
            "from": frm,
            "to": now
        })
        if data.get("s") != "ok":
            return None
        return data
    except Exception:
        return None

def pivot_highs(highs, left=2, right=2):
    pivots = []
    for i in range(left, len(highs) - right):
        h = highs[i]
        if all(h > highs[i - j] for j in range(1, left + 1)) and all(h >= highs[i + j] for j in range(1, right + 1)):
            pivots.append(h)
    return pivots

def nearest_resistance_from_candles(candles, last_price: float) -> float | None:
    highs = candles.get("h") or []
    if not highs:
        return None
    pivs = pivot_highs(highs, 2, 2)
    above = sorted([p for p in pivs if p > last_price])
    if above:
        return float(above[0])
    # fallback
    tail = highs[-50:] if len(highs) >= 50 else highs
    return float(max(tail)) if tail else None

def approx_day_volume_from_candles(candles) -> float:
    # حجم تقريبي من مجموع فوليوم شموع 3 دقائق في نافذة LOOKBACK_BARS
    vols = candles.get("v") or []
    return float(sum(vols)) if vols else 0.0

def build_levels(entry: float):
    stop = round(entry * (1 - STOP_PCT), 4)
    targets = [round(entry * (1 + p), 4) for p in TARGET_PCTS]
    return stop, targets

def main_loop():
    syms = load_universe()
    if not syms:
        raise RuntimeError("Universe is empty. Finnhub stock/symbol failed.")

    tg_send("✅ بوت الزخم شغال (Finnhub فقط - بدون أخبار)")

    while True:
        try:
            sent = get_today_count()
            logging.info("Heartbeat... daily_sent=%s universe=%s", sent, len(syms))

            if sent >= MAX_SIGNALS_PER_DAY:
                time.sleep(POLL_SECONDS)
                continue

            i = get_cursor()
            batch = []
            for _ in range(BATCH_SIZE):
                batch.append(syms[i % len(syms)])
                i += 1
            set_cursor(i)

            for sym in batch:
                if get_today_count() >= MAX_SIGNALS_PER_DAY:
                    break

                # Dedup per symbol/day
                day = today_key()
                k = hashlib.sha1(f"{day}|{sym}".encode("utf-8")).hexdigest()
                if seen_before(k):
                    continue

                q = get_quote(sym)
                time.sleep(SLEEP_BETWEEN_CALLS)
                if not q:
                    continue
                last_price, prev_close, chg_pct = q

                if not (PRICE_MIN <= last_price <= PRICE_MAX):
                    continue
                if chg_pct < MIN_DAY_CHANGE_PCT:
                    continue

                candles = get_candles_3m(sym)
                time.sleep(SLEEP_BETWEEN_CALLS)
                if not candles:
                    continue

                day_vol = approx_day_volume_from_candles(candles)
                if day_vol < MIN_DAY_VOLUME:
                    mark_seen(k)
                    continue

                res = nearest_resistance_from_candles(candles, last_price)
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

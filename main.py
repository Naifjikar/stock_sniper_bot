import os, time, json, hashlib, sqlite3, logging, re
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
import requests

# ===== ENV =====
TG_TOKEN = (os.getenv("TG_TOKEN") or "").strip()
TG_CHAT_ID = (os.getenv("TG_CHAT_ID") or "").strip()

# قناة تنبيه الهدف الأول (اختياري). إذا ما حطيته بيستخدم نفس قناة TG_CHAT_ID
TG_ALERT_CHAT_ID = (os.getenv("TG_ALERT_CHAT_ID") or "").strip()

# تنظيف أي أحرف خفية من المفتاح
MASSIVE_API_KEY = re.sub(r"[^\x20-\x7E]", "", (os.getenv("MASSIVE_API_KEY") or "")).strip()

def req(name, val):
    if not val:
        raise RuntimeError(f"Missing ENV var: {name}")

req("TG_TOKEN", TG_TOKEN)
req("TG_CHAT_ID", TG_CHAT_ID)
req("MASSIVE_API_KEY", MASSIVE_API_KEY)

# ===== SETTINGS =====
PRICE_MIN = 1.0
PRICE_MAX = 10.0

MIN_DAY_CHANGE_PCT = 10.0
MIN_DAY_VOLUME = 300_000

# وقت التشغيل: من 12 الظهر إلى 12 الليل (توقيت الرياض)
RIYADH_TZ = ZoneInfo("Asia/Riyadh")
RUN_START_HOUR = 12   # 12:00
RUN_END_HOUR   = 24   # 24:00 (نعتبرها نهاية اليوم)

# إرسال فوري بدون دفعات + فاصل بين التوصيات
POLL_SECONDS = 60
MIN_MINUTES_BETWEEN_SIGNALS = 15

# نجيب مقاومة من فاصل 10 دقائق
CANDLE_RES_MIN = 10
LOOKBACK_BARS = 180  # 180 شمعة × 10د = 30 ساعة تقريبًا (كفاية)

# الوقف والهدف الأول حسب طلبك
STOP_PCT = 0.08
TARGET1_PCT = 0.07
# نخلي 3 أهداف (عمودي 1/2/3)
TARGET_PCTS = [0.07, 0.15, 0.25]

MAX_SIGNALS_PER_DAY = 4
SLEEP_BETWEEN_CALLS = 0.25

# شرط مهم لتجنب “زخم متأخر”: الدخول لازم يكون قريب من السعر الحالي
# مثال: لا نرسل إذا الدخول أعلى من السعر بأكثر من 5%
MAX_ENTRY_DISTANCE_PCT = 0.05

# تنبيه تحقق الهدف الأول؟
ALERT_ON_TARGET1 = True

# API
API_BASE = "https://api.massive.com"   # الرسمي الجديد
# API_BASE = "https://api.polygon.io"  # شغال برضو

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ===== DB =====
con = sqlite3.connect("seen.db")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS seen (k TEXT PRIMARY KEY, ts INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS daily (d TEXT PRIMARY KEY, n INTEGER, last_send_ts INTEGER)")
cur.execute("""
CREATE TABLE IF NOT EXISTS signals (
  d TEXT,
  sym TEXT,
  entry REAL,
  stop REAL,
  t1 REAL,
  t2 REAL,
  t3 REAL,
  hit1 INTEGER DEFAULT 0,
  PRIMARY KEY (d, sym)
)
""")
con.commit()

def today_key() -> str:
    # نثبت اليوم على توقيت الرياض
    return datetime.now(RIYADH_TZ).date().isoformat()

def now_riyadh():
    return datetime.now(RIYADH_TZ)

def in_run_window() -> bool:
    t = now_riyadh()
    h = t.hour
    # من 12 إلى 24
    return (h >= RUN_START_HOUR) and (h < RUN_END_HOUR)

def get_today_count() -> int:
    d = today_key()
    cur.execute("SELECT n FROM daily WHERE d=?", (d,))
    row = cur.fetchone()
    return int(row[0]) if row else 0

def get_last_send_ts() -> int:
    d = today_key()
    cur.execute("SELECT last_send_ts FROM daily WHERE d=?", (d,))
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0

def set_last_send_ts(ts: int):
    d = today_key()
    n = get_today_count()
    cur.execute("INSERT OR REPLACE INTO daily (d, n, last_send_ts) VALUES (?, ?, ?)", (d, n, ts))
    con.commit()

def inc_today_count():
    d = today_key()
    n = get_today_count() + 1
    last_ts = get_last_send_ts()
    cur.execute("INSERT OR REPLACE INTO daily (d, n, last_send_ts) VALUES (?, ?, ?)", (d, n, last_ts))
    con.commit()

def seen_before(key: str) -> bool:
    cur.execute("SELECT 1 FROM seen WHERE k=?", (key,))
    return cur.fetchone() is not None

def mark_seen(key: str):
    cur.execute("INSERT OR REPLACE INTO seen (k, ts) VALUES (?,?)", (key, int(time.time())))
    con.commit()

# ===== Telegram =====
def tg_send(text: str, chat_id: str | None = None):
    chat_id = chat_id or TG_CHAT_ID
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 429:
            try:
                wait = r.json().get("parameters", {}).get("retry_after", 5)
            except Exception:
                wait = 5
            time.sleep(wait + 1)
            return tg_send(text, chat_id=chat_id)
        if not r.ok:
            logging.error("TG ERROR %s %s", r.status_code, r.text)
    except Exception as e:
        logging.error("TG SEND FAILED: %s", e)

# ===== Massive/Polygon =====
def massive_get(path: str, params: dict | None = None):
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {MASSIVE_API_KEY}"}
    r = requests.get(url, params=params or {}, headers=headers, timeout=25)

    if r.status_code == 429:
        time.sleep(1.2)
        return massive_get(path, params)

    r.raise_for_status()
    return r.json()

def get_top_gainers(limit: int = 30) -> list[dict]:
    data = massive_get("/v2/snapshot/locale/us/markets/stocks/gainers", {})
    tickers = data.get("tickers") or []
    return tickers[:limit]

def get_aggs(symbol: str):
    now = datetime.now(timezone.utc)
    frm = now - timedelta(minutes=CANDLE_RES_MIN * LOOKBACK_BARS)
    to_ms = int(now.timestamp() * 1000)
    from_ms = int(frm.timestamp() * 1000)

    path = f"/v2/aggs/ticker/{symbol}/range/{CANDLE_RES_MIN}/minute/{from_ms}/{to_ms}"
    data = massive_get(path, {"adjusted": "false", "sort": "asc", "limit": 50000})
    results = data.get("results") or []
    return results if results else None

def get_snapshot_ticker(symbol: str) -> dict | None:
    # Snapshot لتحديث السعر ومتابعة الهدف الأول
    path = f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
    try:
        return massive_get(path, {})
    except Exception as e:
        logging.warning("snapshot ticker failed %s: %s", symbol, e)
        return None

def pivot_highs(highs, left=2, right=2):
    pivots = []
    for i in range(left, len(highs) - right):
        h = highs[i]
        if all(h > highs[i - j] for j in range(1, left + 1)) and \
           all(h >= highs[i + j] for j in range(1, right + 1)):
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

    tail = highs[-40:] if len(highs) >= 40 else highs
    return float(max(tail)) if tail else None

def r2(x: float) -> float:
    # رقمين بعد الفاصلة فقط
    return round(float(x), 2)

def build_levels(entry: float):
    stop = r2(entry * (1 - STOP_PCT))
    t1 = r2(entry * (1 + TARGET_PCTS[0]))
    t2 = r2(entry * (1 + TARGET_PCTS[1]))
    t3 = r2(entry * (1 + TARGET_PCTS[2]))
    return stop, (t1, t2, t3)

def snapshot_fields(t: dict):
    sym = (t.get("ticker") or "").strip().upper()
    day = t.get("day") or {}
    prev = t.get("prevDay") or {}

    last_price = float(day.get("c") or 0)
    day_vol = float(day.get("v") or 0)
    prev_close = float(prev.get("c") or 0)

    chg_pct = t.get("todaysChangePerc")
    if chg_pct is None and last_price > 0 and prev_close > 0:
        chg_pct = (last_price - prev_close) / prev_close * 100.0

    try:
        chg_pct = float(chg_pct or 0)
    except Exception:
        chg_pct = 0.0

    return sym, last_price, prev_close, chg_pct, day_vol

def can_send_now() -> bool:
    last_ts = get_last_send_ts()
    if not last_ts:
        return True
    mins = (time.time() - last_ts) / 60.0
    return mins >= MIN_MINUTES_BETWEEN_SIGNALS

def save_signal(sym: str, entry: float, stop: float, t1: float, t2: float, t3: float):
    d = today_key()
    cur.execute(
        "INSERT OR REPLACE INTO signals (d, sym, entry, stop, t1, t2, t3, hit1) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT hit1 FROM signals WHERE d=? AND sym=?),0))",
        (d, sym, entry, stop, t1, t2, t3, d, sym)
    )
    con.commit()

def mark_hit1(sym: str):
    d = today_key()
    cur.execute("UPDATE signals SET hit1=1 WHERE d=? AND sym=?", (d, sym))
    con.commit()

def check_target1_hits():
    if not ALERT_ON_TARGET1:
        return
    d = today_key()
    cur.execute("SELECT sym, t1, entry FROM signals WHERE d=? AND hit1=0", (d,))
    rows = cur.fetchall()
    for sym, t1, entry in rows:
        snap = get_snapshot_ticker(sym)
        time.sleep(SLEEP_BETWEEN_CALLS)
        if not snap:
            continue
        ticker = snap.get("ticker") or {}
        day = (ticker.get("day") or {})
        last_price = float(day.get("c") or 0)
        if last_price and float(last_price) >= float(t1):
            msg = (
                f"{sym}\n"
                f"✅ حقق الهدف الأول\n"
                f"سعره الآن: {r2(last_price)}\n"
                f"الدخول: {r2(entry)}"
            )
            tg_send(msg, chat_id=(TG_ALERT_CHAT_ID or TG_CHAT_ID))
            mark_hit1(sym)

def main_loop():
    tg_send("✅ بوت الزخم شغال (Massive/Polygon)")
    logging.info("MASSIVE_API_KEY len=%d", len(MASSIVE_API_KEY))

    while True:
        try:
            # نافذة التشغيل
            if not in_run_window():
                logging.info("Outside run window (12:00-24:00 Riyadh). Sleeping...")
                time.sleep(POLL_SECONDS)
                continue

            sent = get_today_count()
            logging.info("Heartbeat... daily_sent=%s", sent)

            # تنبيهات الهدف الأول (خفيفة)
            check_target1_hits()

            if sent >= MAX_SIGNALS_PER_DAY:
                time.sleep(POLL_SECONDS)
                continue

            if not can_send_now():
                time.sleep(POLL_SECONDS)
                continue

            gainers = get_top_gainers(limit=30)

            for t in gainers:
                if get_today_count() >= MAX_SIGNALS_PER_DAY:
                    break
                if not can_send_now():
                    break

                sym, last_price, prev_close, chg_pct, day_vol = snapshot_fields(t)
                if not sym or last_price <= 0:
                    continue

                # منع تكرار نفس السهم في نفس اليوم (فقط بعد إرسال توصية)
                k = hashlib.sha1(f"{today_key()}|{sym}".encode("utf-8")).hexdigest()
                if seen_before(k):
                    continue

                # فلترة أساسية (لا نعلم seen هنا حتى نسمح يتحسن لاحقًا)
                if not (PRICE_MIN <= last_price <= PRICE_MAX):
                    continue
                if chg_pct < MIN_DAY_CHANGE_PCT:
                    continue
                if day_vol < MIN_DAY_VOLUME:
                    continue

                aggs = get_aggs(sym)
                time.sleep(SLEEP_BETWEEN_CALLS)
                if not aggs:
                    continue

                res = nearest_resistance_from_aggs(aggs, last_price)
                if not res:
                    continue

                entry = r2(res)

                # شرط “مقاومة قريبة” + تجنب الزخم المتأخر
                dist = (entry - last_price) / last_price
                if dist > MAX_ENTRY_DISTANCE_PCT:
                    continue

                stop, (t1, t2, t3) = build_levels(entry)

                # رسالة حسب طلبك: بدون زخم/فوليوم، فقط سعره الآن ثم الدخول
                msg = (
                    f"{sym}\n"
                    f"سعره الآن: {r2(last_price)}\n"
                    f"الدخول: {entry}\n"
                    f"الوقف: {stop}\n"
                    f"الأهداف:\n"
                    f"1 {t1}\n"
                    f"2 {t2}\n"
                    f"3 {t3}"
                )

                tg_send(msg)
                save_signal(sym, entry, stop, t1, t2, t3)

                mark_seen(k)
                inc_today_count()
                set_last_send_ts(int(time.time()))
                time.sleep(2)

        except Exception as e:
            logging.exception(e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main_loop()

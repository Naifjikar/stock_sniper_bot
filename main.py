import os, time, json, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

MIN_PRICE = 0.01
MAX_PRICE = 10.0
MIN_VOLUME = 5_000_000
MIN_CHANGE_PCT = 15

TAKE_PROFIT_PCT = 7
STOP_LOSS_PCT = 9

EMA_PERIOD = 50
HOURS_BACK = 24 * 5
MAX_SIGNALS_PER_RUN = 5

STATE_FILE = "state.json"
NO_MATCH_COOLDOWN_MIN = 60
SIGNAL_COOLDOWN_MIN = 120  # لا تعيد نفس السهم قبل 120 دقيقة

def now_ts():
    return int(time.time())

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_no_match_ts": 0, "last_signal_ts": {}}
    try:
        return json.load(open(STATE_FILE, "r", encoding="utf-8"))
    except:
        return {"last_no_match_ts": 0, "last_signal_ts": {}}

def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

def polygon_gainers():
    url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers"
    params = {"apiKey": POLYGON_API_KEY}
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()

    out = []
    for item in data.get("tickers", []):
        sym = item.get("ticker")
        last_trade = item.get("lastTrade") or {}
        day = item.get("day") or {}
        prev = item.get("prevDay") or {}

        price = last_trade.get("p") or day.get("c")
        vol = day.get("v")

        # ✅ التغيير الصحيح
        chg = item.get("todaysChangePerc")
        if chg is None:
            dc = day.get("c")
            pc = prev.get("c")
            if dc and pc and pc != 0:
                chg = ((dc - pc) / pc) * 100

        if price is None or vol is None or chg is None:
            continue

        price = float(price)
        vol = int(vol)
        chg = float(chg)

        if MIN_PRICE <= price <= MAX_PRICE and vol >= MIN_VOLUME and chg >= MIN_CHANGE_PCT:
            out.append({"symbol": sym, "price": price, "volume": vol, "change_pct": chg})

    return out

def get_4h_candles(symbol: str):
    end = datetime.utcnow()
    start = end - timedelta(hours=HOURS_BACK)
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/4/hour/{start:%Y-%m-%d}/{end:%Y-%m-%d}"
    params = {"adjusted": "true", "limit": 500, "sort": "asc", "apiKey": POLYGON_API_KEY}
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json().get("results", []) or []

def calc_ema(closes, period):
    if len(closes) < period:
        return None
    sma = sum(closes[:period]) / period
    k = 2 / (period + 1)
    ema = sma
    for p in closes[period:]:
        ema = p * k + ema * (1 - k)
    return ema

def ema50_and_res(symbol: str):
    candles = get_4h_candles(symbol)
    if not candles:
        return None, None
    closes = [float(c["c"]) for c in candles]
    highs  = [float(c["h"]) for c in candles]

    ema50 = calc_ema(closes, EMA_PERIOD)
    if ema50 is None:
        return None, None

    lookback = min(20, len(highs))
    resistance = max(highs[-lookback:])
    return ema50, resistance

def build_msg(stock):
    sym = stock["symbol"]
    cur = stock["price"]

    ema50, res = ema50_and_res(sym)
    if ema50 is None or res is None:
        return None
    if cur <= ema50:
        return None

    entry = round(res, 2)
    target = round(entry * (1 + TAKE_PROFIT_PCT/100), 2)
    stop = round(entry * (1 - STOP_LOSS_PCT/100), 2)

    return f"""📈 <b>سهم زخم: {sym}</b>

السعر الحالي: <b>{cur:.2f}</b>
نقطة الدخول (مقاومة): <b>{entry}</b>

🎯 الهدف: <b>{target}</b>
🛡 الوقف: <b>{stop}</b>

الشروط:
- تغيير اليوم ≥ {MIN_CHANGE_PCT}%
- فوليوم ≥ {MIN_VOLUME:,}
- السعر بين {MIN_PRICE}$ و {MAX_PRICE}$
- فوق EMA50 (4H)
"""

def run_once():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not POLYGON_API_KEY:
        raise SystemExit("Missing env vars: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID / POLYGON_API_KEY")

    state = load_state()
    t = now_ts()

    stocks = polygon_gainers()

    if not stocks:
        if t - int(state.get("last_no_match_ts", 0)) >= NO_MATCH_COOLDOWN_MIN * 60:
            tg_send("لا توجد حالياً أسهم مطابقة لشروط الزخم.")
            state["last_no_match_ts"] = t
            save_state(state)
        return

    sent = 0
    last_signal_ts = state.get("last_signal_ts", {})

    for st in stocks:
        if sent >= MAX_SIGNALS_PER_RUN:
            break

        sym = st["symbol"]
        last = int(last_signal_ts.get(sym, 0))
        if t - last < SIGNAL_COOLDOWN_MIN * 60:
            continue

        msg = build_msg(st)
        if msg:
            tg_send(msg)
            last_signal_ts[sym] = t
            sent += 1
            time.sleep(1.2)

    state["last_signal_ts"] = last_signal_ts
    save_state(state)

if __name__ == "__main__":
    run_once()

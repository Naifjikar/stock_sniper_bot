import requests
from datetime import datetime, timedelta
import time

# ------------ الإعدادات -------------
BOT_TOKEN = "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk"
CHANNEL_ID = -1002608482349
POLYGON_API_KEY = "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq"

# الشروط
MIN_PRICE = 1
MAX_PRICE = 10
MIN_VOLUME = 5_000_000
MIN_CHANGE_PCT = 15   # زخم 15%
TIMEFRAME_HOURS = 16  # 4 ساعات × 4 شموع في اليوم = 16 ساعة


# ---------- إرسال تيليجرام ----------
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    requests.post(url, data=data)


# ---------- جلب أسهم الزخم ----------
def get_momentum_stocks():
    url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers"
    params = {"apiKey": POLYGON_API_KEY}
    r = requests.get(url, params=params).json()

    results = []
    for item in r.get("tickers", []):
        symbol = item["ticker"]
        price = item["last"]["price"]
        volume = item["day"]["v"]
        change_pct = item["day"]["c"]

        if (
            MIN_PRICE <= price <= MAX_PRICE and
            volume >= MIN_VOLUME and
            change_pct >= MIN_CHANGE_PCT
        ):
            results.append({
                "symbol": symbol,
                "price": price
            })
    return results


# ---------- جلب شموع 4 ساعات ----------
def get_4h_candles(symbol):
    end = datetime.utcnow()
    start = end - timedelta(hours=TIMEFRAME_HOURS)

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/"
        f"240/minute/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
    )

    params = {
        "adjusted": "true",
        "limit": 200,
        "sort": "asc",
        "apiKey": POLYGON_API_KEY
    }

    r = requests.get(url, params=params).json()
    return r.get("results", [])


# ---------- حساب SMA50 ----------
def calc_sma50(candles):
    if len(candles) < 50:
        return None
    closes = [c["c"] for c in candles[-50:]]
    return sum(closes) / len(closes)


# ---------- حساب المقاومة ----------
def get_resistance(candles):
    highs = [c["h"] for c in candles]
    return max(highs) if highs else None


# ---------- بناء التوصية ----------
def build_signal(symbol, price):
    candles = get_4h_candles(symbol)
    if not candles:
        return None

    # متوسط 50
    sma50 = calc_sma50(candles)
    if sma50 is None:
        return None

    # شرط السعر فوق SMA50
    if price <= sma50:
        return None

    # المقاومة
    resistance = get_resistance(candles)
    if resistance is None:
        return None

    # الدخول = كسر المقاومة مباشرة
    entry = round(resistance, 2)

    # الهدف والوقف
    target = round(entry * 1.07, 2)
    stop = round(entry * 0.91, 2)

    msg = f"""
📈 <b>سهم: {symbol}</b>

السعر الحالي: {round(price, 2)}
متوسط 50 (4 ساعات): {round(sma50, 2)}
المقاومة: {entry}

🎯 <b>الهدف:</b> {target}  (+7%)
🛡 <b>الوقف:</b> {stop}   (-9%)
"""

    return msg


# ---------- تشغيل البوت ----------
def run_bot():
    stocks = get_momentum_stocks()
    if not stocks:
        send_telegram_message("لا توجد أسهم مطابقة للشروط حالياً.")
        return

    for s in stocks:
        signal_msg = build_signal(s["symbol"], s["price"])
        if signal_msg:
            send_telegram_message(signal_msg)
            time.sleep(1)


if __name__ == "__main__":
    run_bot()

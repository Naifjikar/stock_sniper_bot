import requests
from datetime import datetime, timedelta
import time

# ===================== الإعدادات الأساسية =====================

BOT_TOKEN = "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk"
CHANNEL_ID = -1002608482349
POLYGON_API_KEY = "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq"

# نطاق الأسعار (من سنت إلى 10 دولار)
MIN_PRICE = 0.01
MAX_PRICE = 10.0

# شروط الزخم
MIN_VOLUME = 5_000_000        # أقل فوليوم يومي
MIN_CHANGE_PCT = 15           # أقل نسبة ارتفاع (٪)

# الهدف والوقف
TAKE_PROFIT_PCT = 7           # هدف +7٪
STOP_LOSS_PCT = 9             # وقف -9٪

# إعدادات EMA
EMA_PERIOD = 50               # EMA50
HOURS_BACK = 24 * 5           # نرجع 5 أيام للخلف تقريباً على فاصل 4 ساعات

# حد أعلى لعدد التوصيات لكل تشغيل
MAX_SIGNALS_PER_RUN = 5


# ===================== دوال مساعدة =====================

def send_telegram_message(text: str):
    """إرسال رسالة إلى قناة تيليجرام."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


def get_momentum_stocks():
    """
    جلب أسهم الزخم من Polygon (top gainers)
    مع فلترة السعر والفوليوم ونسبة التغيير.
    """
    url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers"
    params = {"apiKey": POLYGON_API_KEY}

    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
    except Exception as e:
        print(f"Error fetching gainers: {e}")
        return []

    results = []
    for item in data.get("tickers", []):
        symbol = item.get("ticker")

        # نحاول نجيب السعر من أكثر من مكان
        last_trade = item.get("lastTrade") or {}
        last_quote = item.get("lastQuote") or {}
        day_info = item.get("day") or {}

        price = last_trade.get("p") or last_quote.get("p") or day_info.get("c")
        volume = day_info.get("v")
        change_pct = day_info.get("c")

        if price is None or volume is None or change_pct is None:
            continue

        # فلترة السعر والفوليوم والزخم
        if (
            MIN_PRICE <= price <= MAX_PRICE and
            volume >= MIN_VOLUME and
            change_pct >= MIN_CHANGE_PCT
        ):
            results.append({
                "symbol": symbol,
                "price": float(price),
                "volume": int(volume),
                "change_pct": float(change_pct)
            })

    return results


def get_4h_candles(symbol: str):
    """
    جلب شموع فاصل 4 ساعات من Polygon.
    نرجع عدة أيام للخلف لبناء EMA50.
    """
    end = datetime.utcnow()
    start = end - timedelta(hours=HOURS_BACK)

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/"
        f"4/hour/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
    )

    params = {
        "adjusted": "true",
        "limit": 500,
        "sort": "asc",
        "apiKey": POLYGON_API_KEY
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
    except Exception as e:
        print(f"Error fetching candles for {symbol}: {e}")
        return []

    return data.get("results", [])


def calc_ema(closes, period=EMA_PERIOD):
    """حساب EMA بسيط من قائمة الأسعار الإغلاق."""
    if len(closes) < period:
        return None

    k = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
    return ema


def get_ema50_and_resistance(symbol: str):
    """
    - يحسب EMA50 من إغلاقات فاصل 4 ساعات
    - يحسب المقاومة كأعلى هاي في آخر عدد من الشموع
    """
    candles = get_4h_candles(symbol)
    if not candles:
        return None, None

    closes = [float(c["c"]) for c in candles]
    highs = [float(c["h"]) for c in candles]

    ema50 = calc_ema(closes, EMA_PERIOD)
    if ema50 is None:
        return None, None

    # نأخذ المقاومة كأعلى هاي في آخر 20 شمعة مثلاً
    lookback = min(20, len(highs))
    resistance = max(highs[-lookback:])

    return ema50, resistance


def build_signal(stock):
    """
    ينشئ رسالة التوصية لسهم واحد:
    - يتأكد أن السعر فوق EMA50 (4 ساعات)
    - يحسب الهدف والوقف
    """
    symbol = stock["symbol"]
    current_price = stock["price"]

    ema50, resistance = get_ema50_and_resistance(symbol)
    if ema50 is None or resistance is None:
        return None

    # شرط أن السعر الحالي فوق EMA50
    if current_price <= ema50:
        return None

    entry = round(resistance, 2)

    # الهدف والوقف
    target = round(entry * (1 + TAKE_PROFIT_PCT / 100), 2)
    stop = round(entry * (1 - STOP_LOSS_PCT / 100), 2)

    msg = f"""
📈 <b>سهم زخم: {symbol}</b>

السعر الحالي: <b>{current_price:.2f}</b>
EMA50 (فاصل 4 ساعات): <b>{ema50:.2f}</b>
المقاومة المحددة (نقطة الدخول): <b>{entry}</b>

🎯 <b>الهدف:</b> {target}  (+{TAKE_PROFIT_PCT}%)
🛡 <b>الوقف:</b> {stop}   (-{STOP_LOSS_PCT}%)

🔊 شروط الاختيار:
- ارتفاع اليوم: ≥ {MIN_CHANGE_PCT}%
- فوليوم: ≥ {MIN_VOLUME:,} سهم
- السعر بين {MIN_PRICE}$ و {MAX_PRICE}$
- فوق EMA50 على فاصل 4 ساعات
"""

    return msg.strip()


def run_bot_once():
    """
    تشغيل البوت مرة واحدة:
    - جلب أسهم الزخم
    - فلترتها على EMA50
    - إرسال حتى MAX_SIGNALS_PER_RUN توصية
    """
    stocks = get_momentum_stocks()
    if not stocks:
        send_telegram_message("لا توجد حالياً أسهم مطابقة لشروط الزخم.")
        return

    sent = 0
    for stock in stocks:
        if sent >= MAX_SIGNALS_PER_RUN:
            break

        signal_msg = build_signal(stock)
        if signal_msg:
            send_telegram_message(signal_msg)
            sent += 1
            time.sleep(1)  # مهلة بسيطة بين الرسائل

    if sent == 0:
        send_telegram_message("تم فحص الأسهم ولا يوجد سهم يطابق شروط EMA50 والمقاومة حالياً.")


if __name__ == "__main__":
    # تشغيل مرّة واحدة
    run_bot_once()

    # لو حاب يشغّل طول اليوم على Render كـ background job:
    # while True:
    #     run_bot_once()
    #     time.sleep(15 * 60)  # كل 15 دقيقة

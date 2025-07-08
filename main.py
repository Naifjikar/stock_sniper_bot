import requests
import time
from telegram import Bot

BOT_TOKEN = "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk"
CHANNEL_ID = "-1002608482349"
FINNHUB_API = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

bot = Bot(token=BOT_TOKEN)
sent_tickers = set()

def get_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_API}"
    try:
        res = requests.get(url).json()
        return [s["symbol"] for s in res if s.get("type") == "Common Stock"]
    except Exception as e:
        print("❌ Error fetching symbols:", e)
        return []

def passes_filters(symbol):
    try:
        q = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API}"
        res = requests.get(q).json()

        c = res.get("c", 0)  # current price
        pc = res.get("pc", 0)  # previous close
        o = res.get("o", 0)  # open
        v = res.get("v", 0)  # volume

        if not all([c, pc, o, v]) or c < 1 or c > 5:
            return False

        pct_from_open = ((c - o) / o) * 100
        pct_from_close = ((c - pc) / pc) * 100

        url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={FINNHUB_API}"
        metric = requests.get(url).json().get("metric", {})
        avg_vol_10d = metric.get("10DayAverageTradingVolume", 1)

        if (
            pct_from_open >= 10 and
            pct_from_close >= 0 and
            v >= 5_000_000 and
            v >= avg_vol_10d * 5
        ):
            return True
    except:
        pass
    return False

def get_vwap(symbol):
    try:
        url = f"https://finnhub.io/api/v1/indicator?symbol={symbol}&resolution=3&indicator=vwap&token={FINNHUB_API}"
        res = requests.get(url).json()
        if "vwap" in res and res["vwap"]:
            return round(res["vwap"][-1], 2)
    except:
        pass
    return None

def send_recommendation(symbol, entry):
    targets = [round(entry * (1 + i / 100), 2) for i in [0.08, 0.15, 0.25, 0.40]]
    stop = round(entry * 0.91, 2)

    message = f"""🚨 توصية اليوم 🚨

📉 سهم: {symbol}
📥 دخول: {entry}
🎯 أهداف:
- {targets[0]}
- {targets[1]}
- {targets[2]}
- {targets[3]}
⛔️ وقف: {stop}

#توصيات_الأسهم"""

    bot.send_message(chat_id=CHANNEL_ID, text=message)
    print(f"✅ تم إرسال {symbol}")

def run_bot():
    print("🚀 بدأ التشغيل...")
    symbols = get_stocks()
    print(f"📊 عدد الأسهم للفحص: {len(symbols)}")

    for symbol in symbols:
        if symbol in sent_tickers:
            continue
        if passes_filters(symbol):
            entry = get_vwap(symbol)
            if entry:
                send_recommendation(symbol, entry)
                sent_tickers.add(symbol)
        time.sleep(0.5)  # لتجنب حظر API

while True:
    run_bot()
    print("⏳ في انتظار الفحص القادم...")
    time.sleep(1800)  # كل 30 دقيقة

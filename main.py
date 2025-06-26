import requests
import asyncio
from telegram import Bot
from datetime import datetime
import pytz

BOT_TOKEN = "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk"
PRIVATE_CHANNEL = "-1002608482349"
POLYGON_API = "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq"
FINNHUB_API = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

bot = Bot(token=BOT_TOKEN)
sent_tickers = set()

def fetch_gainers():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_API}"
    try:
        res = requests.get(url).json()
        print("🔗 رد API Polygon:", res)  # <== تشخيص
        return res.get("tickers", [])
    except Exception as e:
        print("❌ خطأ في جلب الأسهم:", e)
        return []

def get_resistance(ticker):
    try:
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={ticker}&resolution=3&count=100&token={FINNHUB_API}"
        res = requests.get(url).json()
        print(f"📈 رد الشموع من Finnhub لـ {ticker}:", res)  # <== تشخيص
        if res.get("s") != "ok":
            return None
        highs = res.get("h", [])
        closes = res.get("c", [])
        if not highs or not closes:
            return None
        last_close = closes[-1]
        resistances = [h for h in highs if h > last_close and h - last_close < 0.3]
        if resistances:
            return round(min(resistances), 2)
    except Exception as e:
        print(f"❌ خطأ في get_resistance لـ {ticker}:", e)
    return None

def get_vwap(ticker):
    try:
        url = f"https://finnhub.io/api/v1/indicator?symbol={ticker}&resolution=3&indicator=vwap&token={FINNHUB_API}"
        res = requests.get(url).json()
        print(f"📉 رد VWAP من Finnhub لـ {ticker}:", res)  # <== تشخيص
        if "vwap" in res and res["vwap"]:
            return round(res["vwap"][-1], 2)
    except Exception as e:
        print(f"❌ خطأ في get_vwap لـ {ticker}:", e)
    return None

def generate_message(ticker, entry):
    targets = [round(entry * (1 + i / 100), 2) for i in [0.08, 0.15, 0.25, 0.40]]
    stop = round(entry * 0.91, 2)
    return f"""🚨 توصية اليوم 🚨

📉 سهم: {ticker}
📥 دخول: {entry}
🎯 أهداف:
- {targets[0]}
- {targets[1]}
- {targets[2]}
- {targets[3]}
⛔️ وقف: {stop}

#توصيات_الأسهم"""

def within_trading_hours():
    now = datetime.now(pytz.timezone("Asia/Riyadh"))
    start = now.replace(hour=11, minute=0, second=0, microsecond=0)
    end = now.replace(hour=22, minute=30, second=0, microsecond=0)
    return start <= now <= end

async def check_and_send():
    print("📡 البوت شغال ويبحث عن توصيات...")  # <== تأكيد الشغل

    if not within_trading_hours():
        print("⏳ خارج وقت التداول. البوت ينتظر...")
        return

    gainers = fetch_gainers()
    print(f"📊 عدد الأسهم من API: {len(gainers)}")

    for stock in gainers:
        ticker = stock["ticker"]
        price = stock["lastTrade"]["p"]
        volume = stock["day"]["v"]
        open_price = stock["day"]["o"]
        prev_close = stock["prevDay"]["c"]
        avg_vol = stock["day"]["av"]

        print(f"🔎 فحص السهم: {ticker} | السعر الحالي: {price}")

        if (
            0.1 <= price <= 1000 and
            volume >= 5_000_000 and
            price > prev_close and
            ((price - open_price) / open_price) * 100 > 10 and
            volume > avg_vol * 5 and
            ticker not in sent_tickers
        ):
            resistance = get_resistance(ticker)
            if resistance:
                entry = resistance
            else:
                vwap = get_vwap(ticker)
                entry = round(vwap if vwap else price * 1.05, 2)

            msg = generate_message(ticker, entry)
            await bot.send_message(chat_id=PRIVATE_CHANNEL, text=msg)
            print(f"✅ تم إرسال توصية لـ {ticker} عند {entry}")
            sent_tickers.add(ticker)

async def main_loop():
    while True:
        await check_and_send()
        await asyncio.sleep(120)

asyncio.run(main_loop())

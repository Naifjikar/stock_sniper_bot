import requests
import asyncio
from telegram import Bot
from datetime import datetime
import pytz

BOT_TOKEN = "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk"
PRIVATE_CHANNEL = "-1002608482349"
FINNHUB_API = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

bot = Bot(token=BOT_TOKEN)
sent_tickers = set()

def fetch_gainers():
    url = "https://quotes-gw.webullfintech.com/api/information/securities/top?regionId=6&topSecType=1"
    headers = {"accept": "application/json", "User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers).json()
        results = []
        for item in res.get("data", []):
            try:
                ticker = item["ticker"]
                price = float(item["lastDone"])
                volume = float(item["volume"])
                change = float(item["chgRate"])
                open_price = float(item["open"])
                prev_close = float(item["close"])
                results.append({
                    "ticker": ticker,
                    "price": price,
                    "volume": volume,
                    "change": change,
                    "open_price": open_price,
                    "prev_close": prev_close,
                })
            except Exception as e:
                print("⚠️ Error parsing stock item:", e)
                continue
        return results
    except Exception as e:
        print("❌ Webull Gainers error:", e)
        return []

def get_prev_high(ticker):
    try:
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={ticker}&resolution=5&count=2&token={FINNHUB_API}"
        res = requests.get(url).json()
        if res.get("s") != "ok":
            return None
        highs = res.get("h", [])
        if len(highs) >= 2:
            return highs[-2]
    except Exception as e:
        print(f"❌ Error get_prev_high for {ticker}:", e)
    return None

def get_resistance(ticker):
    try:
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={ticker}&resolution=3&count=100&token={FINNHUB_API}"
        res = requests.get(url).json()
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
        print(f"❌ Error get_resistance for {ticker}:", e)
    return None

def get_vwap(ticker):
    try:
        url = f"https://finnhub.io/api/v1/indicator?symbol={ticker}&resolution=3&indicator=vwap&token={FINNHUB_API}"
        res = requests.get(url).json()
        if "vwap" in res and res["vwap"]:
            return round(res["vwap"][-1], 2)
    except Exception as e:
        print(f"❌ Error get_vwap for {ticker}:", e)
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
    print("📡 بدأ الفحص")

    if not within_trading_hours():
        print("⏳ السوق مغلق حالياً")
        return

    gainers = fetch_gainers()
    print(f"📊 تم جلب {len(gainers)} سهم من Webull")

    for stock in gainers:
        ticker = stock["ticker"]
        price = stock["price"]
        volume = stock["volume"]
        change = stock["change"]
        open_price = stock["open_price"]
        prev_close = stock["prev_close"]

        print(f"🔍 فحص {ticker} - السعر: {price}, الحجم: {volume}, التغير: {change}%")

        if (
            1 <= price <= 10 and
            volume >= 700_000 and
            price > prev_close and
            ((price - open_price) / open_price) * 100 >= 10 and
            change >= 10 and
            ticker not in sent_tickers
        ):
            print(f"✅ {ticker} اجتاز الفلترة الأولى")

            prev_high = get_prev_high(ticker)
            if prev_high:
                print(f"📈 هاي أمس: {prev_high}")
            if prev_high and price <= prev_high:
                print(f"⛔️ {ticker} لم يتجاوز هاي أمس")
                continue

            resistance = get_resistance(ticker)
            entry = resistance if resistance else get_vwap(ticker)
            if not entry:
                entry = round(price * 1.05, 2)

            print(f"📥 نقطة الدخول: {entry}")
            msg = generate_message(ticker, entry)
            await bot.send_message(chat_id=PRIVATE_CHANNEL, text=msg)
            print(f"📨 تم الإرسال: {ticker} ✅")
            sent_tickers.add(ticker)
        else:
            print(f"❌ {ticker} لم يطابق الشروط")

async def main_loop():
    print("🚀 بدأ التشغيل الكامل للبوت...")
    while True:
        await check_and_send()
        await asyncio.sleep(20)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("🛑 تم إيقاف البوت يدويًا")

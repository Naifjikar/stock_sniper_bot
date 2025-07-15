import asyncio
import requests
from telegram import Bot
from datetime import datetime, timedelta
import pytz

TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'
POLYGON_KEY = 'ht3apHm7nJA2VhvBynMHEcpRI11VSRbq'

bot = Bot(token=TOKEN)

def get_filtered_stocks():
    # تحديد توقيت السعودية
    now = datetime.now(pytz.timezone('Asia/Riyadh'))
    hour = now.hour
    minute = now.minute

    # قبل 4:30 مساءً = بري ماركت
    if hour < 16 or (hour == 16 and minute < 30):
        url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/pre-market/gainers?apiKey={POLYGON_KEY}"
        print("📈 المصدر: البري ماركت")
    else:
        url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_KEY}"
        print("📊 المصدر: السوق الرسمي")

    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        tickers = data.get("tickers", [])
        print(f"✅ تم جلب {len(tickers)} سهم")
    except Exception as e:
        print(f"❌ خطأ في API: {e}")
        return []

    filtered = []
    for t in tickers:
        symbol = t.get("ticker", "")
        current_price = t.get("lastTrade", {}).get("p", 0)
        open_price = t.get("day", {}).get("o", 0)

        if not symbol or not current_price or not open_price:
            continue

        change = ((current_price - open_price) / open_price) * 100 if open_price else 0

        if 1 <= current_price <= 7 and change >= 10:
            filtered.append(symbol)

    print(f"🎯 بعد الفلترة: {len(filtered)} سهم")
    return filtered

async def main():
    while True:
        stocks = get_filtered_stocks()
        if stocks:
            await bot.send_message(chat_id=CHANNEL_ID, text=f"✅ عدد الأسهم المطابقة: {len(stocks)}")
            for symbol in stocks[:3]:  # أول 3 فقط
                await bot.send_message(chat_id=CHANNEL_ID, text=f"🚀 سهم محتمل: {symbol}")
        else:
            await bot.send_message(chat_id=CHANNEL_ID, text="🚫 لا يوجد أسهم مطابقة حالياً.")
        await asyncio.sleep(300)  # كل 5 دقائق

asyncio.run(main())

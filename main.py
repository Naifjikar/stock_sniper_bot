import asyncio
import requests
from telegram import Bot

# إعدادات البوت
TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'
API_KEY = 'ht3apHm7nJA2VhvBynMHEcpRI11VSRbq'  # مفتاح Polygon

bot = Bot(token=TOKEN)

# فلتر الأسهم - باستخدام Polygon
def get_filtered_stocks_polygon():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json().get("tickers", [])
    except Exception as e:
        print("❌ خطأ في جلب البيانات:", e)
        return []

    filtered = []
    for stock in data:
        try:
            symbol = stock.get("ticker", "")
            price = stock["lastTrade"]["p"]  # السعر الحالي
            change_perc = stock.get("todaysChangePerc", 0)  # نسبة التغير اليومية %

            if 1 <= price <= 7 and change_perc >= 10:
                filtered.append(symbol)

            if len(filtered) >= 3:
                break
        except:
            continue

    return filtered

# حلقة التشغيل كل 5 دقائق
async def main():
    while True:
        stocks = get_filtered_stocks_polygon()

        if stocks:
            first = stocks[0]
            await bot.send_message(chat_id=CHANNEL_ID, text=f"🚀 بداية انطلاق: ${first}")

        await asyncio.sleep(300)  # كل 5 دقائق (300 ثانية)

# تشغيل الكود
asyncio.run(main())

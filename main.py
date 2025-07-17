import asyncio
import requests
from telegram import Bot

# إعدادات البوت و API
TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'
POLYGON_KEY = 'ht3apHm7nJA2VhvBynMHEcpRI11VSRbq'

bot = Bot(token=TOKEN)

# فلترة الأسهم
def get_filtered_stocks():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_KEY}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        tickers = data.get("tickers", [])
        print(f"\n✅ جلب البيانات: {len(tickers)} سهم\n")
    except Exception as e:
        print(f"❌ خطأ في API: {e}")
        return []

    filtered = []
    for t in tickers:
        symbol = t.get("ticker", "")
        current_price = t.get("lastTrade", {}).get("p", 0)
        open_price = t.get("day", {}).get("o", 0)

        # نطبع بيانات كل سهم لمراقبة المشكلة
        print(f"{symbol} | السعر: {current_price} | الافتتاح: {open_price}")

        if not symbol or not current_price or not open_price:
            continue

        try:
            change = ((current_price - open_price) / open_price) * 100
        except ZeroDivisionError:
            continue

        # شرط بسيط مؤقت للتجربة
        if 1 <= current_price <= 7 and change >= 10:
            filtered.append((symbol, round(current_price, 2), round(change, 2)))

    print(f"\n📊 بعد الفلترة: {len(filtered)} سهم مطابق\n")
    return filtered

# المهام الرئيسية
async def main():
    while True:
        stocks = get_filtered_stocks()
        if stocks:
            await bot.send_message(chat_id=CHANNEL_ID, text=f"✅ عدد الأسهم المطابقة: {len(stocks)}")
            for symbol, price, change in stocks[:3]:
                await bot.send_message(chat_id=CHANNEL_ID, text=f"🚀 {symbol}\nالسعر: {price}\nالتغيير: {change}%")
        await asyncio.sleep(300)  # كل 5 دقائق

asyncio.run(main())

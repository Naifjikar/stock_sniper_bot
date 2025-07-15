import asyncio
import requests
from telegram import Bot

TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'
POLYGON_KEY = 'ht3apHm7nJA2VhvBynMHEcpRI11VSRbq'

bot = Bot(token=TOKEN)

def get_filtered_stocks():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_KEY}"
    try:
        data = requests.get(url, timeout=10).json()
        tickers = data.get("tickers", [])
    except Exception as e:
        print(f"❌ خطأ في جلب البيانات: {e}")
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

    return filtered

async def main():
    while True:
        stocks = get_filtered_stocks()
        if stocks:
            for symbol in stocks:
                await bot.send_message(chat_id=CHANNEL_ID, text=f"🚀 سهم محتمل: {symbol}")
        await asyncio.sleep(300)  # كل 5 دقايق
        

asyncio.run(main())

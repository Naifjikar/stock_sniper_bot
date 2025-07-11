import asyncio
import requests
from telegram import Bot

TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

bot = Bot(token=TOKEN)

def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        data = requests.get(url, timeout=10).json()
    except Exception as e:
        print(f"❌ خطأ في جلب الرموز: {e}")
        return []

    filtered = []

    for sym in data:
        symbol = sym.get("symbol", "")
        if not symbol or "." in symbol:
            continue

        try:
            quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            quote = requests.get(quote_url, timeout=10).json()

            c = quote.get("c", 0)      # السعر الحالي
            o = quote.get("o", 0)      # سعر الافتتاح

            # نحسب نسبة التغير من الافتتاح
            change = ((c - o) / o) * 100 if o else 0

            if 1 <= c <= 7 and change >= 10:
                filtered.append(symbol)

            if len(filtered) >= 3:
                break

        except Exception:
            continue

    return filtered

async def main():
    while True:
        stocks = get_filtered_stocks()

        if stocks:
            first = stocks[0]
            await bot.send_message(chat_id=CHANNEL_ID, text=f"🚀 بداية انطلاق: ${first}")
        else:
            await bot.send_message(chat_id=CHANNEL_ID, text="❌ لا يوجد أسهم مطابقة حالياً.")

        await asyncio.sleep(300)  # كل 5 دقائق

asyncio.run(main())

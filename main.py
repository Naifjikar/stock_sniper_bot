import asyncio
import requests
from telegram import Bot

TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

bot = Bot(token=TOKEN)

# دالة الفلترة
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

            c = quote.get("c", 0)
            pc = quote.get("pc", 0)

            if 1 <= c <= 5 and c > pc:
                print(f"✅ {symbol} | السعر: {c} > إغلاق أمس: {pc}")
                filtered.append(symbol)

            if len(filtered) >= 3:
                break

        except Exception as e:
            print(f"⚠️ خطأ في {symbol}: {e}")
            continue

    return filtered

# الدالة الرئيسية
async def main():
    pass  # لسه ما نفذنا شيء، بس تأكد أنه يشتغل بدون خطأ

# تشغيل الكود
asyncio.run(main())

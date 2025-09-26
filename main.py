import os, asyncio, aiohttp
from telegram import Bot

# مفاتيح
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk")
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1002608482349")

BASE = "https://api.polygon.io"
bot = Bot(token=TOKEN)

async def fetch_json(session, url, params=None):
    if params is None:
        params = {}
    params["apiKey"] = POLYGON_API_KEY
    async with session.get(url, params=params, timeout=20) as r:
        return await r.json()

async def get_top_gainers(session, limit=100):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/gainers"
    data = await fetch_json(session, url)
    return [t["ticker"] for t in data.get("tickers", [])[:limit]]

async def get_last_price(session, symbol):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
    data = await fetch_json(session, url)
    try:
        return float(data["ticker"]["lastTrade"]["p"])
    except Exception:
        return None

async def get_prev_close(session, symbol):
    url = f"{BASE}/v2/aggs/ticker/{symbol}/prev"
    data = await fetch_json(session, url)
    try:
        return float(data["results"][0]["c"])
    except Exception:
        return None

def pct_from_prev(last, prev):
    if not prev or prev == 0:
        return 0.0
    return (last / prev - 1.0) * 100.0

async def send_telegram_message(msg: str):
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=msg)
    except Exception as e:
        print("خطأ في إرسال الرسالة:", e)

async def main():
    async with aiohttp.ClientSession() as session:
        symbols = await get_top_gainers(session, limit=100)
        if not symbols:
            print("مافيه رموز حالياً")
            return

        sent = 0
        for sym in symbols:
            if sent >= 5:   # حد أقصى 5 أسهم
                break

            last = await get_last_price(session, sym)
            prev = await get_prev_close(session, sym)

            # تحقق من القيم
            if last is None or prev is None:
                continue

            if not (1.0 <= last <= 10.0):
                continue

            change = pct_from_prev(last, prev)
            if change >= 30.0:  # شرط نسبة الصعود من إغلاق أمس
                msg = (
                    f"سهم مطابق ✅\n\n"
                    f"{sym}\n"
                    f"السعر الآن: {last:.2f}\n"
                    f"إغلاق أمس: {prev:.2f}\n"
                    f"التغير عن إغلاق أمس: {change:.1f}%"
                )
                await send_telegram_message(msg)
                print("تم الإرسال:", sym)
                sent += 1

        if sent == 0:
            print("ما وجدنا سهم يطابق الشروط")

if __name__ == "__main__":
    asyncio.run(main())

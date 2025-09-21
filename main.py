import os, asyncio, aiohttp, datetime as dt
from telegram import Bot

# مفاتيح
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk")
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1002608482349")

BASE = "https://api.polygon.io"
bot = Bot(token=TOKEN)

async def fetch_json(session, url, params=None):
    if params is None: params = {}
    params["apiKey"] = POLYGON_API_KEY
    async with session.get(url, params=params, timeout=20) as r:
        return await r.json()

async def get_top_gainers(session, limit=80):
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

async def get_today_open(session, symbol):
    today = dt.datetime.utcnow().date()
    url = f"{BASE}/v2/aggs/ticker/{symbol}/range/1/day/{today}/{today}"
    data = await fetch_json(session, url, params={"adjusted":"true","sort":"asc","limit":1})
    try:
        return float(data["results"][0]["o"])
    except Exception:
        return None

def pct_from_open(last, open_px):
    if not open_px or open_px == 0: return 0.0
    return (last / open_px - 1.0) * 100.0

async def main():
    async with aiohttp.ClientSession() as session:
        symbols = await get_top_gainers(session, limit=80)
        if not symbols:
            print("مافيه رموز حالياً"); return

        for sym in symbols:
            last = await get_last_price(session, sym)
            if last is None or not (1.00 <= last <= 5.00):
                continue  # شرط 1

            prev = await get_prev_close(session, sym)
            if prev is None or last < prev:
                continue  # شرط 2

            open_px = await get_today_open(session, sym)
            if open_px is None:
                continue
            change = pct_from_open(last, open_px)
            if change >= 10.0:  # شرط 3
                msg = (
                    f"سهم مطابق ✅\n\n"
                    f"{sym}\n"
                    f"السعر الآن: {last:.2f}\n"
                    f"إغلاق أمس: {prev:.2f}\n"
                    f"التغير من الافتتاح: {change:.1f}%"
                )
                await bot.send_message(chat_id=CHANNEL_ID, text=msg)
                print("تم الإرسال:", sym)
                return

        print("ما وجدنا سهم يطابق الشروط")

if __name__ == "__main__":
    asyncio.run(main())

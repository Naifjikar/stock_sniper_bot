import os, asyncio, aiohttp
from telegram import Bot

# مفاتيح
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk")
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1002608482349")

BASE = "https://api.polygon.io"
bot = Bot(token=TOKEN)  # v13.15 -> دوال متزامنة (Sync)

async def fetch_json(session, url, params=None):
    if params is None:
        params = {}
    params["apiKey"] = POLYGON_API_KEY
    try:
        async with session.get(url, params=params, timeout=20) as r:
            r.raise_for_status()
            return await r.json()
    except Exception as e:
        print(f"HTTP error @ {url}: {e}")
        return {}

async def get_top_gainers(session, limit=100):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/gainers"
    data = await fetch_json(session, url)
    return [t.get("ticker") for t in data.get("tickers", [])[:limit] if t.get("ticker")]

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

async def send_telegram_message(text: str):
    # v13.15: send_message متزامنة، نشغّلها في thread حتى ما نحظر الحدث
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, bot.send_message, CHANNEL_ID, text)

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
            if last is None or not (1.00 <= last <= 10.00):
                continue  # شرط السعر

            prev = await get_prev_close(session, sym)
            if prev is None:
                continue

            change = pct_from_prev(last, prev)
            if change >= 30.0:  # شرط نسبة الصعود من إغلاق أمس (مناسب للبري ماركت)
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

import os, asyncio, aiohttp, time, datetime as dt
from telegram import Bot

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq")
TOKEN           = os.getenv("TELEGRAM_BOT_TOKEN", "8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk")
CHANNEL_ID      = os.getenv("CHANNEL_ID", "-1002608482349")

BASE = "https://api.polygon.io"
bot  = Bot(token=TOKEN)

def now():
    import datetime as _dt
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def fetch_json(session, url, params=None):
    if params is None:
        params = {}
    params["apiKey"] = POLYGON_API_KEY
    try:
        async with session.get(url, params=params, timeout=20) as r:
            r.raise_for_status()
            return await r.json()
    except Exception as e:
        print(f"[{now()}] fetch_json ERROR {url}: {e}")
        return {}

def pct_from_prev(last, prev):
    if not prev or prev == 0:
        return 0.0
    return (last / prev - 1.0) * 100.0

async def send_telegram_message(msg: str):
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=msg)
        await asyncio.sleep(0.6)
    except Exception as e:
        print(f"[{now()}] خطأ في إرسال الرسالة: {e}")

async def get_top_gainers(session, limit=100):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/gainers"
    data = await fetch_json(session, url)
    tickers = data.get("tickers", []) or []
    return [t.get("ticker") for t in tickers if t.get("ticker")][:limit]

async def get_last_price(session, symbol):
    url = f"{BASE}/v2/last/trade/{symbol}"
    data = await fetch_json(session, url)
    try:
        if "results" in data and isinstance(data["results"], dict):
            return float(data["results"].get("p"))
        if "last" in data and isinstance(data["last"], dict):
            return float(data["last"].get("price"))
        return float(data.get("ticker", {}).get("lastTrade", {}).get("p"))
    except Exception:
        return None

async def get_prev_close_and_prev_volume(session, symbol):
    url = f"{BASE}/v2/aggs/ticker/{symbol}/prev"
    data = await fetch_json(session, url)
    try:
        res = (data.get("results") or [])[0]
        return float(res.get("c")), float(res.get("v") or 0)
    except Exception:
        return None, None

async def get_today_volume(session, symbol):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
    data = await fetch_json(session, url)
    try:
        return float(data.get("ticker", {}).get("day", {}).get("v") or 0)
    except Exception:
        return 0.0

async def run_once(min_pct=30.0, price_min=1.0, price_max=10.0, max_symbols=5, min_volume=5_000_000):
    print(f"[{now()}] تشغيل الفلتر...")
    sent = 0
    async with aiohttp.ClientSession() as session:
        symbols = await get_top_gainers(session, limit=100)
        if not symbols:
            print(f"[{now()}] ما فيه رموز حالياً (gainers فارغة)")
            return

        for sym in symbols:
            if sent >= max_symbols:
                break

            last  = await get_last_price(session, sym)
            prev, prev_vol = await get_prev_close_and_prev_volume(session, sym)
            if last is None or prev is None:
                continue

            if not (price_min <= last <= price_max):
                continue

            change = pct_from_prev(last, prev)
            if change < min_pct:
                continue

            today_vol = await get_today_volume(session, sym)
            if today_vol < min_volume and (prev_vol or 0) < min_volume:
                continue

            # === هنا الإرسال يكون "رمز فقط" ===
            await send_telegram_message(sym)
            print(f"[{now()}] تم الإرسال: {sym} ({change:.1f}%)")
            sent += 1

    if sent == 0:
        print(f"[{now()}] ما وجدنا سهم يطابق الشروط")

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(run_once(
                min_pct=30.0,      # شرط الصعود من إغلاق أمس
                price_min=1.0,     # أدنى سعر
                price_max=10.0,    # أعلى سعر
                max_symbols=5,     # حد أقصى للمرسَل في الدورة
                min_volume=5_000_000  # حجم تداول أدنى (اليوم أو أمس)
            ))
        except Exception as e:
            print(f"[{now()}] FATAL LOOP ERROR: {e}")
        time.sleep(180)  # كل 3 دقائق

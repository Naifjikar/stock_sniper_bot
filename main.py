import os, asyncio, aiohttp, time, datetime as dt
from telegram import Bot

# ========= ENV VARS =========
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
TOKEN           = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID      = os.getenv("CHANNEL_ID")

assert POLYGON_API_KEY, "❌ POLYGON_API_KEY مفقود"
assert TOKEN, "❌ TELEGRAM_BOT_TOKEN مفقود"
assert CHANNEL_ID, "❌ CHANNEL_ID مفقود"

BASE = "https://api.polygon.io"
bot  = Bot(token=TOKEN)

# ========= UTIL =========
def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

# ========= POLYGON QUERIES =========
async def get_top_gainers(session, limit=100):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/gainers"
    data = await fetch_json(session, url)
    tickers = data.get("tickers", []) or []
    return [t.get("ticker") for t in tickers if t.get("ticker")][:limit]

async def get_last_price(session, symbol):
    """يحاول last/trade أولاً (المدفوع). عند فشل/403 يهبط إلى snapshot."""
    # 1) last/trade
    url_last = f"{BASE}/v2/last/trade/{symbol}"
    data = await fetch_json(session, url_last)
    try:
        if isinstance(data.get("results"), dict) and data["results"].get("p"):
            return float(data["results"]["p"])
        if isinstance(data.get("last"), dict) and data["last"].get("price"):
            return float(data["last"]["price"])
        if data.get("status") == "ERROR":
            raise RuntimeError(data.get("error", "status ERROR"))
    except Exception:
        pass
    # 2) snapshot fallback
    url_snap = f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
    snap = await fetch_json(session, url_snap)
    try:
        return float(snap["ticker"]["lastTrade"]["p"])
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

# ========= ONE RUN =========
async def run_once(min_pct=30.0, price_min=1.0, price_max=10.0, max_symbols=5, min_volume=5_000_000):
    print(f"[{now()}] تشغيل الفلتر...")
    sent = 0
    async with aiohttp.ClientSession() as session:
        # اختبار سريع للمفتاح عند أول تشغيل فقط (AAPL)
        try:
            test_price = await get_last_price(session, "AAPL")
            print(f"[{now()}] TEST AAPL last_price={test_price}")
        except Exception as e:
            print(f"[{now()}] TEST ERROR: {e}")

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

            # يرسل الرمز فقط
            await send_telegram_message(sym)
            print(f"[{now()}] تم الإرسال: {sym} ({change:.1f}%)")
            sent += 1

    if sent == 0:
        print(f"[{now()}] ما وجدنا سهم يطابق الشروط")

# ========= LOOP EVERY 3 MIN =========
if __name__ == "__main__":
    while True:
        try:
            asyncio.run(run_once(
                min_pct=30.0,
                price_min=1.0,
                price_max=10.0,
                max_symbols=5,
                min_volume=5_000_000
            ))
        except Exception as e:
            print(f"[{now()}] FATAL LOOP ERROR: {e}")
        time.sleep(180)

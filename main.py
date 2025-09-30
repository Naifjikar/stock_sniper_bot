# main.py
import os, asyncio, aiohttp, time, datetime as dt, contextlib
from telegram import Bot
from aiohttp import web

# ========= ENV VARS =========
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
TOKEN           = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID      = os.getenv("CHANNEL_ID", "")

BASE = "https://api.polygon.io"
bot  = Bot(token=TOKEN)

# ========= UTILS =========
def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def env_ready():
    missing = []
    if not POLYGON_API_KEY: missing.append("POLYGON_API_KEY")
    if not TOKEN:           missing.append("TELEGRAM_BOT_TOKEN")
    if not CHANNEL_ID:      missing.append("CHANNEL_ID")
    if missing:
        print(f"[{now()}] ⚠️ Environment missing: {', '.join(missing)}")
        return False
    return True

async def fetch_json(session, url, params=None):
    if params is None:
        params = {}
    params["apiKey"] = POLYGON_API_KEY
    try:
        async with session.get(url, params=params, timeout=20) as r:
            r.raise_for_status()
            return await r.json()
    except Exception as e:
        print(f"[{now()}] ❌ fetch_json ERROR {url}: {e}")
        return {}

def pct_from_prev(last, prev):
    if not prev or prev == 0:
        return 0.0
    return (last / prev - 1.0) * 100.0

async def send_telegram_message(msg: str):
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"[{now()}] ✅ أُرسلت رسالة تيليجرام: {msg}")
        await asyncio.sleep(0.4)
    except Exception as e:
        print(f"[{now()}] ❌ خطأ إرسال تيليجرام: {e}")

# ========= POLYGON (Snapshot-only) =========
async def get_top_gainers(session, limit=100):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/gainers"
    data = await fetch_json(session, url)
    tickers = data.get("tickers", []) or []
    symbols = [t.get("ticker") for t in tickers if t.get("ticker")]
    print(f"[{now()}] ℹ️ عدد الـ gainers المستلمة: {len(symbols)}")
    return symbols[:limit]

async def get_last_price(session, symbol):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
    data = await fetch_json(session, url)
    try:
        return float(data["ticker"]["lastTrade"]["p"])
    except Exception:
        print(f"[{now()}] ⚠️ lastPrice غير متوفر لـ {symbol}")
        return None

async def get_prev_close_and_prev_volume(session, symbol):
    url = f"{BASE}/v2/aggs/ticker/{symbol}/prev"
    data = await fetch_json(session, url)
    try:
        res = (data.get("results") or [])[0]
        prev_close = float(res.get("c"))
        prev_vol   = float(res.get("v") or 0)
        return prev_close, prev_vol
    except Exception:
        print(f"[{now()}] ⚠️ prev/vol غير متوفر لـ {symbol}")
        return None, None

async def get_today_volume(session, symbol):
    url = f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
    data = await fetch_json(session, url)
    try:
        return float(data.get("ticker", {}).get("day", {}).get("v") or 0)
    except Exception:
        return 0.0

# ========= ONE RUN (فلترة دورة واحدة) =========
async def run_once(
    min_pct=30.0, price_min=1.0, price_max=10.0,
    max_symbols=5, min_volume=5_000_000
):
    if not env_ready():
        return

    print(f"[{now()}] 🚀 بدء دورة فلترة جديدة...")
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
            print(f"[{now()}] فحص {sym} -> last={last}, prev={prev}")

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

            # إرسال: الرمز فقط
            await send_telegram_message(sym)
            print(f"[{now()}] ✅ تم الإرسال: {sym} ({change:.1f}%)")
            sent += 1

    if sent == 0:
        print(f"[{now()}] ❌ ما وجدنا سهم يطابق الشروط")

# ========= Web Service على Render + تشغيل اللوب بالخلفية =========
async def start_background_tasks(app):
    async def runner():
        while True:
            try:
                await run_once(
                    min_pct=30.0,
                    price_min=1.0,
                    price_max=10.0,
                    max_symbols=5,
                    min_volume=1_000_000
                )
            except Exception as e:
                print(f"[{now()}] FATAL LOOP ERROR: {e}")
            await asyncio.sleep(180)  # كل 3 دقائق
    app['task'] = asyncio.create_task(runner())

async def cleanup_background_tasks(app):
    app['task'].cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await app['task']

async def health(request):
    return web.Response(text="OK")

app = web.Application()
app.router.add_get('/', health)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"[{now()}] 🌐 Running web app on port {port} (Render healthcheck) + background loop...")
    web.run_app(app, port=port)

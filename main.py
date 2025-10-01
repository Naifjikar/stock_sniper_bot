import os, asyncio, datetime as dt
from aiohttp import web
from telegram import Bot

# === ENV VARS ===
TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")

bot = Bot(token=TOKEN)

def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def send_tg(text: str):
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=text)
        print(f"[{now()}] ✅ TG sent: {text}")
        await asyncio.sleep(0.2)
        return True
    except Exception as e:
        print(f"[{now()}] ❌ TG error: {e}")
        return False

# === HTTP Handlers ===
async def health(_):
    return web.Response(text="OK step3")

async def test(_):
    ok = await send_tg("✅ Bot alive (step3 test)")
    return web.Response(text="sent" if ok else "fail")

# === App ===
app = web.Application()
app.router.add_get("/", health)
app.router.add_get("/test", test)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"[{now()}] 🌐 step3 running on :{port}")
    web.run_app(app, port=port)

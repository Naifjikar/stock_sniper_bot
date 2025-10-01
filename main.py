import os
from aiohttp import web
import datetime as dt

# === ENV VARS ===
TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")

def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def env_ready():
    missing = []
    if not TOKEN: missing.append("TELEGRAM_BOT_TOKEN")
    if not CHANNEL_ID: missing.append("CHANNEL_ID")
    if not POLYGON_API_KEY: missing.append("POLYGON_API_KEY")
    if missing:
        return f"⚠️ MISSING: {', '.join(missing)}"
    return "✅ All ENV OK"

# === HTTP Handlers ===
async def health(_):
    return web.Response(text="OK step2")

async def check_env(_):
    return web.Response(text=env_ready())

# === App ===
app = web.Application()
app.router.add_get("/", health)
app.router.add_get("/env", check_env)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"[{now()}] 🌐 step2 running on :{port}")
    web.run_app(app, port=port)

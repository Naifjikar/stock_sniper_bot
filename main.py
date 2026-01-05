import asyncio, requests, time, json, os
from telegram import Bot
from deep_translator import GoogleTranslator

# ================== CONFIG ==================
TOKEN = "8101036051:AAEMbhWIYv22FOMV6pXcAOosEWxsy9v3jfY"
CHANNEL = "@USMarketnow"
POLYGON_KEY = "ht3apHm7nJA2VhvBynMHEcpRI11VSRbq"

PRICE_MIN, PRICE_MAX = 0.3, 10.0
INTERVAL = 90
STATE_FILE = "stocks_state.json"

bot = Bot(token=TOKEN)
translator = GoogleTranslator(source="auto", target="ar")

state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}

# ================== FILTERS ==================
STRONG_KEYWORDS = [
    "fda", "approval", "clinical", "trial", "phase",
    "acquisition", "merger", "agreement", "contract",
    "earnings", "revenue", "eps", "guidance",
    "launch", "technology", "ai", "patent"
]

BLOCK = [
    "lawsuit", "class action", "investigation",
    "law firm", "shareholder"
]

# ================== HELPERS ==================
def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def polygon(path, params=None):
    params = params or {}
    params["apiKey"] = POLYGON_KEY
    r = requests.get("https://api.polygon.io" + path, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def get_price(sym):
    try:
        snap = polygon(f"/v2/snapshot/locale/us/markets/stocks/tickers/{sym}")
        return float(snap["ticker"]["day"]["c"])
    except:
        return None

def get_levels(sym):
    try:
        bars = polygon(
            f"/v2/aggs/ticker/{sym}/range/3/minute",
            {"limit": 20}
        )["results"]

        highs = [b["h"] for b in bars]
        lows = [b["l"] for b in bars]

        resistance = max(highs)
        stop = min(lows[-5:])  # آخر قاع فني

        return resistance, stop
    except:
        return None, None

# ================== MAIN LOOP ==================
async def run():
    while True:
        try:
            news = polygon("/v2/reference/news", {"limit": 50})["results"]

            for n in news:
                uid = n["id"]
                if uid in state:
                    continue

                title = n["title"].lower()
                if any(b in title for b in BLOCK):
                    state[uid] = time.time()
                    continue

                if not any(k in title for k in STRONG_KEYWORDS):
                    state[uid] = time.time()
                    continue

                for sym in n.get("tickers", []):
                    price = get_price(sym)
                    if not price or not (PRICE_MIN <= price <= PRICE_MAX):
                        continue

                    res, stop = get_levels(sym)
                    if not res or not stop or stop >= res:
                        continue

                    entry = res
                    t1 = entry * 1.08
                    t2 = entry * 1.15
                    t3 = entry * 1.25
                    t4 = entry * 1.40

                    title_ar = translator.translate(n["title"])

                    msg = f"""
🚨 <b>{sym}</b>
📰 {title_ar}

📍 الدخول: {entry:.2f}
⛔ الوقف: {stop:.2f}

🎯 الأهداف:
1️⃣ {t1:.2f}
2️⃣ {t2:.2f}
3️⃣ {t3:.2f}
4️⃣ {t4:.2f}
"""

                    await bot.send_message(
                        chat_id=CHANNEL,
                        text=msg,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )

                    state[uid] = time.time()
                    save_state()
                    await asyncio.sleep(180)
                    break

        except Exception as e:
            print("ERR:", e)

        await asyncio.sleep(INTERVAL)

asyncio.run(run())

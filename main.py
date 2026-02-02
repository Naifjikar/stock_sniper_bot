import os, time, json, requests
from datetime import datetime, timezone, timedelta

# ================= CONFIG =================
TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FINNHUB = os.getenv("FINNHUB_KEY")

PRICE_MIN = 1
PRICE_MAX = 10
MAX_PICKS = 5

STATE_FILE = "state.json"
KSA = timezone(timedelta(hours=3))

# ================= HELPERS =================
def tg_send(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text})

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"sent": {}, "results": {}}

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), indent=2)

def get_quote(symbol):
    r = requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": symbol, "token": FINNHUB},
        timeout=10
    )
    return r.json()

def get_watchlist():
    # تحط هنا قائمة مراقبة أو تجيبها من API خارجي
    return ["SOUN","BNZI","INTZ","MULN","HOLO","TSLA"]

# ================= MAIN =================
state = load_state()
today = datetime.now(KSA).strftime("%Y-%m-%d")

picked_today = [s for s in state["sent"] if state["sent"][s]==today]

for symbol in get_watchlist():
    if len(picked_today) >= MAX_PICKS:
        break

    if symbol in picked_today:
        continue

    q = get_quote(symbol)
    price = q["c"]
    prev = q["pc"]

    if price <= 0 or prev <= 0:
        continue

    change = ((price - prev) / prev) * 100

    if not (PRICE_MIN <= price <= PRICE_MAX):
        continue

    if change < 8:
        continue

    entry = round(price, 2)
    stop = round(entry * 0.91, 2)

    targets = [
        round(entry * 1.08, 2),
        round(entry * 1.15, 2),
        round(entry * 1.25, 2),
        round(entry * 1.40, 2),
    ]

    msg = f"""
{symbol}
دخول: {entry}
وقف: {stop}
الأهداف:
{targets[0]} - {targets[1]} - {targets[2]} - {targets[3]}
""".strip()

    tg_send(msg)

    state["sent"][symbol] = today
    state["results"][symbol] = {"entry": entry, "high": entry}
    picked_today.append(symbol)
    save_state(state)

    time.sleep(2)

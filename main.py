import requests
import time
import datetime
import pytz
import telegram

# إعدادات البوت
TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
bot = telegram.Bot(token=TOKEN)

# مفتاح API
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

# توقيت السعودية
timezone = pytz.timezone('Asia/Riyadh')

def get_filtered_stocks():
    market_url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    symbols = requests.get(market_url).json()
    filtered = []

    for sym in symbols:
        symbol = sym.get("symbol")
        if not symbol or "." in symbol:
            continue

        quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
        data = requests.get(quote_url).json()

        try:
            c = data.get("c", 0)
            pc = data.get("pc", 0)
            o = data.get("o", 0)
            vol = data.get("v", 0)

            if not all([c, pc, o]):
                continue

            change_from_open = (c - o) / o * 100
            volume_ratio = vol / 1000000

            if (
                1 <= c <= 5 and
                c > pc and
                change_from_open >= 10 and
                volume_ratio >= 5
            ):
                filtered.append(symbol)
                if len(filtered) >= 3:
                    break

        except:
            continue

    print(f"📈 عدد الأسهم المطابقة: {len(filtered)}")
    return filtered

def get_entry_point(symbol):
    url = f"https://finnhub.io/api/v1/indicator?symbol={symbol}&resolution=3&indicator=vwap&token={FINNHUB_KEY}"
    res = requests.get(url).json()
    try:
        last_vwap = res["vwap"][-1]
        return round(last_vwap, 2)
    except:
        return None

def send_recommendation(symbol, entry):
    targets = [
        round(entry + 0.08, 2),
        round(entry + 0.15, 2),
        round(entry + 0.25, 2),
        round(entry + 0.40, 2)
    ]
    stop = round(entry - 0.09, 2)

    msg = f"""
📍 {symbol}
دخول: {entry}
أهداف:
- {targets[0]}
- {targets[1]}
- {targets[2]}
- {targets[3]}
وقف: {stop}
"""
    bot.send_message(chat_id=CHANNEL_ID, text=msg)
    print(f"✅ تم إرسال التوصية: {symbol} | دخول: {entry}")

def run():
    print("📡 بدأ الفحص")
    symbols = get_filtered_stocks()

    for sym in symbols:
        entry = get_entry_point(sym)
        if entry:
            send_recommendation(sym, entry)
        else:
            print(f"❌ لا يوجد VWAP لـ {sym}")

while True:
    run()
    time.sleep(600)

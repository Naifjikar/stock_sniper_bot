import requests
import time
import datetime
import pytz
import telegram

# إعدادات البوت
TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
bot = telegram.Bot(token=TOKEN)

# API Key
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

# توقيت السعودية
timezone = pytz.timezone('Asia/Riyadh')

def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        symbols = requests.get(url, timeout=10).json()
    except:
        print("❌ فشل في جلب الرموز")
        return []

    filtered = []
    for sym in symbols:
        symbol = sym.get("symbol")
        if not symbol or "." in symbol:
            continue
        try:
            q = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            data = requests.get(q, timeout=10).json()
            c, pc, o, v = data.get("c", 0), data.get("pc", 0), data.get("o", 0), data.get("v", 0)

            if not all([c, pc, o]) or v == 0:
                continue

            chg = (c - o) / o * 100
            if 1 <= c <= 5 and c > pc and chg >= 10 and v >= 5_000_000:
                print(f"✅ {symbol} | سعر: {c} | تغيير: {round(chg,2)}% | حجم: {round(v/1_000_000,1)}M")
                filtered.append(symbol)

            if len(filtered) >= 4:
                break
        except Exception as e:
            print(f"⚠️ خطأ {symbol}: {e}")
            continue

    return filtered

def get_vwap(symbol):
    url = f"https://finnhub.io/api/v1/indicator?symbol={symbol}&resolution=3&indicator=vwap&token={FINNHUB_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        return round(res["vwap"][-1], 2)
    except:
        return None

def get_resistance(symbol):
    candles_url = f"https://finnhub.io/api/v1/stock/candle?symbol={symbol}&resolution=3&count=30&token={FINNHUB_KEY}"
    try:
        r = requests.get(candles_url, timeout=10).json()
        if r["s"] != "ok":
            return None
        highs = r["h"][-10:]
        return round(max(highs), 2)
    except:
        return None

def send_recommendation(symbol, entry):
    targets = [round(entry + x, 2) for x in [0.08, 0.15, 0.25, 0.4]]
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
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"📤 تم إرسال التوصية: {symbol}")
    except Exception as e:
        print(f"❌ فشل إرسال {symbol}: {e}")

def run():
    now = datetime.datetime.now(timezone)
    print("📡 بدأ الفحص في:", now.strftime('%Y-%m-%d %H:%M:%S'))
    symbols = get_filtered_stocks()

    for symbol in symbols:
        vwap = get_vwap(symbol)
        res = get_resistance(symbol)
        if vwap and res:
            entry = min(vwap, res)
            send_recommendation(symbol, entry)
        else:
            print(f"🚫 تجاهل {symbol} لعدم توفر VWAP أو مقاومة")

# تشغيل كل 10 دقائق
while True:
    run()
    time.sleep(600)

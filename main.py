import requests
import datetime
import pytz
from telegram import Bot

# إعدادات البوت
TOKEN = "8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw"
CHANNEL_ID = -1002757012569
bot = Bot(token=TOKEN)

# مفتاح Finnhub
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"
FINNHUB_URL = "https://finnhub.io/api/v1"

# المنطقة الزمنية
timezone = pytz.timezone("Asia/Riyadh")
now = datetime.datetime.now(timezone)

def get_filtered_stocks():
    url = f"{FINNHUB_URL}/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        symbols = requests.get(url, timeout=10).json()
    except:
        print("❌ فشل جلب الرموز")
        return []

    filtered = []
    for sym in symbols:
        symbol = sym.get("symbol")
        if not symbol or "." in symbol:
            continue
        try:
            q_url = f"{FINNHUB_URL}/quote?symbol={symbol}&token={FINNHUB_KEY}"
            data = requests.get(q_url, timeout=10).json()
            c = data.get("c", 0)
            pc = data.get("pc", 0)
            o = data.get("o", 0)
            v = data.get("v", 0)
            if not all([c, pc, o]) or c < 1 or c > 5 or c <= pc:
                continue
            if (c - o) / o * 100 >= 10 and v >= 5_000_000:
                filtered.append(symbol)
            if len(filtered) >= 4:
                break
        except:
            continue
    return filtered

def get_entry_price(symbol):
    try:
        vwap_url = f"{FINNHUB_URL}/indicator?symbol={symbol}&resolution=3&indicator=vwap&token={FINNHUB_KEY}"
        res = requests.get(vwap_url, timeout=10).json()
        vwap = res.get("vwap", [])
        if not vwap:
            return None
        return round(vwap[-1], 2)
    except:
        return None

def send_recommendation(symbol, entry):
    t1 = round(entry + 0.08, 2)
    t2 = round(entry + 0.15, 2)
    t3 = round(entry + 0.25, 2)
    t4 = round(entry + 0.40, 2)
    stop = round(entry - 0.09, 2)

    msg = f"""
📈 {symbol}
📥 دخول: {entry}
🎯 أهداف: {t1} - {t2} - {t3} - {t4}
🛑 وقف: {stop}
"""
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=msg.strip())
        print(f"✅ أُرسلت توصية {symbol}")
    except Exception as e:
        print(f"❌ فشل إرسال {symbol}: {e}")

def run():
    bot.send_message(chat_id=CHANNEL_ID, text=f"📡 بدأ الفحص في: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    stocks = get_filtered_stocks()
    for symbol in stocks:
        entry = get_entry_price(symbol)
        if entry:
            send_recommendation(symbol, entry)
        else:
            print(f"🚫 لا يوجد VWAP لـ {symbol}")

if __name__ == "__main__":
    run()

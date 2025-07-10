import requests
import time
import datetime
import pytz
from telegram import Bot

# إعدادات البوت
TOKEN = 'ضع_توكن_البوت_هنا'
CHANNEL_ID = '-100xxxxxxxxxx'  # قناة تيليجرام الخاصة
bot = Bot(token=TOKEN)

# مفتاح API من Finnhub
FINNHUB_KEY = "ضع_مفتاح_API_من_Finnhub"

# توقيت السعودية
timezone = pytz.timezone('Asia/Riyadh')

def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        response = requests.get(url, timeout=15)
        symbols = response.json()
    except:
        print("❌ فشل في جلب الرموز.")
        return []

    filtered = []
    for sym in symbols:
        try:
            symbol = sym.get("symbol")
            if not symbol or "." in symbol:
                continue

            quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            data = requests.get(quote_url, timeout=10).json()

            c = data.get("c", 0)
            pc = data.get("pc", 0)
            o = data.get("o", 0)
            v = data.get("v", 0)

            if not all([c, pc, o]):
                continue

            change = ((c - o) / o) * 100
            if 1 <= c <= 5 and c > pc and change >= 10 and v >= 5_000_000:
                filtered.append(symbol)
                print(f"✅ {symbol} | سعر: {c} | تغيير: {round(change, 2)}% | حجم: {v}")
            if len(filtered) >= 3:
                break
        except Exception as e:
            print(f"⚠️ خطأ في {sym}: {e}")
            continue

    print(f"📈 عدد الأسهم المطابقة: {len(filtered)}")
    return filtered

def get_entry_point(symbol):
    url = f"https://finnhub.io/api/v1/indicator?symbol={symbol}&resolution=3&indicator=vwap&token={FINNHUB_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        last_vwap = res["vwap"][-1]
        return round(last_vwap, 2)
    except:
        print(f"❌ لا يمكن حساب VWAP لـ {symbol}")
        return None

def send_recommendation(symbol, entry):
    targets = [round(entry + 0.08, 2), round(entry + 0.15, 2), round(entry + 0.25, 2), round(entry + 0.40, 2)]
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
    for sym in symbols:
        entry = get_entry_point(sym)
        if entry:
            send_recommendation(sym, entry)
        else:
            print(f"🚫 تجاهل {sym} بسبب عدم وجود نقطة دخول")

# لتشغيل فوري لمرة واحدة
run()

# أو لتكرار كل 10 دقائق
# while True:
#     run()
#     time.sleep(600)

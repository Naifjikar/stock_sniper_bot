import requests
import time
import datetime
import pytz
import telegram

# إعدادات البوت
TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
bot = telegram.Bot(token=TOKEN)

# API من Finnhub
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"
timezone = pytz.timezone('Asia/Riyadh')

def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        symbols = requests.get(url, timeout=10).json()
    except:
        print("❌ فشل في جلب رموز الأسهم")
        return []

    filtered = []
    for sym in symbols:
        try:
            symbol = sym.get("symbol")
            if not symbol or "." in symbol:
                continue

            quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            quote = requests.get(quote_url, timeout=10).json()

            c = quote.get("c", 0)
            pc = quote.get("pc", 0)
            o = quote.get("o", 0)
            v = quote.get("v", 0)

            if not all([c, pc, o, v]):
                continue

            change_from_open = (c - o) / o * 100
            volume_millions = v / 1_000_000

            if 1 <= c <= 5 and c > pc and change_from_open >= 10 and volume_millions >= 5:
                print(f"✅ {symbol} | السعر: {c} | التغير: {round(change_from_open, 2)}% | الحجم: {round(volume_millions, 1)}M")
                filtered.append(symbol)

            if len(filtered) >= 3:
                break

        except Exception as e:
            print(f"⚠️ خطأ في {sym}: {e}")
            continue

    print(f"📈 الأسهم المختارة: {filtered}")
    return filtered

def get_vwap_entry(symbol):
    url = f"https://finnhub.io/api/v1/indicator?symbol={symbol}&resolution=3&indicator=vwap&token={FINNHUB_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        last_vwap = res.get("vwap", [])[-1]
        return round(last_vwap, 2)
    except:
        print(f"❌ لا يوجد VWAP لـ {symbol}")
        return None

def send_signal(symbol, entry):
    targets = [
        round(entry + 0.08, 2),
        round(entry + 0.15, 2),
        round(entry + 0.25, 2),
        round(entry + 0.40, 2),
    ]
    stop = round(entry - 0.09, 2)

    msg = f"""
📊 توصية سهم: {symbol}
دخول: {entry}
أهداف:
- {targets[0]}
- {targets[1]}
- {targets[2]}
- {targets[3]}
وقف الخسارة: {stop}
    """.strip()

    try:
        bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"📤 تم إرسال التوصية لـ {symbol}")
    except Exception as e:
        print(f"❌ فشل إرسال {symbol}: {e}")

def run():
    now = datetime.datetime.now(timezone)
    print("📡 بدأ الفحص في:", now.strftime('%Y-%m-%d %H:%M:%S'))

    symbols = get_filtered_stocks()
    for symbol in symbols:
        entry = get_vwap_entry(symbol)
        if entry:
            send_signal(symbol, entry)
        else:
            print(f"🚫 لا توجد نقطة دخول لـ {symbol}")

# تشغيل مستمر كل 10 دقائق
while True:
    run()
    time.sleep(600)

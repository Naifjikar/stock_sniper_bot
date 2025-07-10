import requests
import time
import datetime
import pytz
import telegram

TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

bot = telegram.Bot(token=TOKEN)
timezone = pytz.timezone('Asia/Riyadh')
sent_today = set()

def get_filtered_stocks():
    try:
        url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
        data = requests.get(url).json()
    except Exception as e:
        print(f"❌ فشل في جلب الرموز: {e}")
        return []

    filtered = []
    for sym in data:
        if not isinstance(sym, dict):
            continue

        symbol = sym.get("symbol", "")
        if not symbol or "." in symbol or symbol in sent_today:
            continue

        try:
            quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            quote = requests.get(quote_url).json()

            c = quote.get("c", 0)
            pc = quote.get("pc", 0)
            o = quote.get("o", 0)
            vol = quote.get("v", 0)

            if not all([c, pc, o]) or vol < 700_000:
                continue

            change = (c - o) / o * 100
            if 1 <= c <= 5 and c > pc and change >= 10:
                print(f"✅ مطابق: {symbol} | السعر: {c} | التغير: {round(change,1)}% | الحجم: {vol}")
                filtered.append(symbol)
        except Exception as e:
            print(f"⚠️ خطأ في {symbol}: {e}")
            continue
    return filtered

def send_alert(symbol):
    msg = f"📢 سهم {symbol} - بداية انطلاق"
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=msg)
        sent_today.add(symbol)
        print(f"📤 أُرسل: {symbol}")
    except Exception as e:
        print(f"❌ فشل الإرسال لـ {symbol}: {e}")

def run():
    now = datetime.datetime.now(timezone)
    print(f"\n📡 بدأ الفحص في: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=f"📡 بدأ الفحص {now.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ فشل إرسال رسالة البدء: {e}")

    symbols = get_filtered_stocks()
    if not symbols:
        print("🚫 لا توجد أسهم مطابقة حالياً.")
    for sym in symbols:
        send_alert(sym)

if __name__ == "__main__":
    while True:
        run()
        time.sleep(600)

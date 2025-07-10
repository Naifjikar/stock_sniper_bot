import requests
import datetime
import pytz
import telegram
import time

# إعدادات البوت
TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
bot = telegram.Bot(token=TOKEN)

# إعدادات المنطقة الزمنية
timezone = pytz.timezone('Asia/Riyadh')

# مفتاح API
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"

# الأسهم التي تم إرسالها اليوم
sent_today = set()
last_reset_date = datetime.datetime.now(timezone).date()


def reset_sent_list_if_new_day():
    global sent_today, last_reset_date
    today = datetime.datetime.now(timezone).date()
    if today != last_reset_date:
        sent_today.clear()
        last_reset_date = today


def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        data = requests.get(url).json()
    except Exception as e:
        print(f"❌ فشل في جلب الرموز: {e}")
        return []

    filtered = []

    for sym in data:
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

            if not all([c, pc, o]) or vol == 0:
                continue

            change = (c - o) / o * 100

            if (
                1 <= c <= 5 and
                c > pc and
                change >= 10 and
                vol > 5_000_000
            ):
                filtered.append(symbol)

        except Exception:
            continue

    return filtered


def send_alert(symbol):
    msg = f"🚀 بداية انطلاق\n📈 السهم: {symbol}"
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"📤 تم إرسال: {symbol}")
        sent_today.add(symbol)
    except Exception as e:
        print(f"❌ فشل إرسال {symbol}: {e}")


def run():
    reset_sent_list_if_new_day()
    stocks = get_filtered_stocks()
    for s in stocks:
        send_alert(s)


# تكرار كل دقيقة
if __name__ == "__main__":
    while True:
        run()
        time.sleep(60)

import requests
import time
import datetime
import pytz
import telegram

# إعدادات البوت
TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
bot = telegram.Bot(token=TOKEN)

# API و توقيت
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"
timezone = pytz.timezone('Asia/Riyadh')
sent_today = set()


def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
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

            if (
                1 <= c <= 5 and
                c > pc and
                change >= 10
            ):
                filtered.append(symbol)

        except:
            continue

    return filtered


def send_alert(symbol):
    message = f"📢 سهم {symbol} - بداية انطلاق"
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=message)
        sent_today.add(symbol)
    except Exception as e:
        print(f"❌ فشل إرسال {symbol}: {e}")


def run():
    now = datetime.datetime.now(timezone)
    print(f"✅ تشغيل الفحص: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    symbols = get_filtered_stocks()
    for sym in symbols:
        send_alert(sym)


if __name__ == "__main__":
    while True:
        run()
        time.sleep(600)  # كل 10 دقائق

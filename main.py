import requests
import time
import datetime
import pytz
import telegram

# إعدادات البوت
TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
bot = telegram.Bot(token=TOKEN)

# API
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"
timezone = pytz.timezone('Asia/Riyadh')


def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        data = requests.get(url).json()
    except Exception as e:
        print(f"❌ فشل في جلب الرموز: {e}")
        return []

    filtered = []

    for sym in data:
        if isinstance(sym, dict):
            symbol = sym.get("symbol", "")
        else:
            continue

        if not symbol or "." in symbol:
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
                print(f"✅ {symbol} | السعر: {c} | التغير: {round(change, 1)}% | الحجم: {round(vol / 1_000_000, 1)}M")
                filtered.append(symbol)

            if len(filtered) >= 3:
                break

        except Exception as e:
            print(f"⚠️ خطأ في {symbol}: {e}")
            continue

    return filtered


def get_vwap_entry(symbol):
    url = f"https://finnhub.io/api/v1/indicator?symbol={symbol}&resolution=3&indicator=vwap&token={FINNHUB_KEY}"
    try:
        res = requests.get(url).json()
        last = res["vwap"][-1]
        return round(last, 2)
    except:
        print(f"🚫 لا يوجد VWAP لـ {symbol}")
        return None


def send_signal(symbol, entry):
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
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"📤 تم إرسال التوصية: {symbol}")
    except Exception as e:
        print(f"❌ فشل إرسال توصية {symbol}: {e}")


def run():
    now = datetime.datetime.now(timezone)
    start_msg = f"📡 بدأ الفحص في: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    print(start_msg)
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=start_msg)
    except Exception as e:
        print(f"❌ فشل إرسال رسالة البدء: {e}")

    symbols = get_filtered_stocks()
    for sym in symbols:
        entry = get_vwap_entry(sym)
        if entry:
            send_signal(sym, entry)
        else:
            print(f"🚫 تجاهل {sym} بسبب عدم وجود نقطة دخول")


if __name__ == "__main__":
    while True:
        run()
        time.sleep(600)  # كل 10 دقائق

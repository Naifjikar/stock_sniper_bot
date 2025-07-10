import requests
import time
import datetime
import pytz

TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"
timezone = pytz.timezone('Asia/Riyadh')


def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL_ID,
        "text": msg
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("❌ فشل إرسال الرسالة:", response.text)
    except Exception as e:
        print("❌ خطأ أثناء إرسال الرسالة:", e)


def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        data = requests.get(url).json()
    except Exception as e:
        print(f"❌ فشل في جلب الرموز: {e}")
        return []

    filtered = []

    for sym in data:
        if isinstance(sym, str):  # تجاوز أي عنصر غير صحيح
            continue

        symbol = sym.get("symbol", "")
        if not symbol or "." in symbol:
            continue

        try:
            quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            quote = requests.get(quote_url).json()

            c = quote.get("c", 0)
            pc = quote.get("pc", 0)
            o = quote.get("o", 0)
            vol = quote.get("v", 0)

            change = (c - o) / o * 100 if o else 0

            if (
                1 <= c <= 5 and
                c > pc and
                change >= 10 and
                vol > 700_000
            ):
                print(f"🚀 بداية انطلاق: {symbol}")
                filtered.append(symbol)

            if len(filtered) >= 3:
                break

        except Exception as e:
            print(f"⚠️ خطأ في {symbol}: {e}")
            continue

    return filtered


def run():
    now = datetime.datetime.now(timezone)
    send_telegram_message(f"📡 بدأ الفحص: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    symbols = get_filtered_stocks()
    for sym in symbols:
        send_telegram_message(f"🚀 سهم بداية انطلاق: {sym}")


if __name__ == "__main__":
    while True:
        run()
        time.sleep(600)

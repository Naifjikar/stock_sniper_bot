import requests
import time
import datetime
import pytz

# إعدادات البوت
TOKEN = '8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw'
CHANNEL_ID = '-1002757012569'
FINNHUB_KEY = "d1dqgr9r01qpp0b3fligd1dqgr9r01qpp0b3flj0"
timezone = pytz.timezone('Asia/Riyadh')

def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        'chat_id': CHANNEL_ID,
        'text': text
    }
    try:
        r = requests.post(url, data=payload)
        print("📬 Telegram response:", r.status_code, r.text)
    except Exception as e:
        print("❌ خطأ في إرسال الرسالة:", e)

def get_filtered_stocks():
    url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
    try:
        data = requests.get(url).json()
    except Exception as e:
        print("❌ فشل تحميل الرموز:", e)
        return []

    filtered = []
    for sym in data:
        if isinstance(sym, str):
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
            v = quote.get("v", 0)

            change = (c - o) / o * 100 if o else 0

            if (
                1 <= c <= 5 and
                c > pc and
                change >= 10 and
                v > 700_000
            ):
                filtered.append(symbol)

            if len(filtered) >= 3:
                break
        except Exception as e:
            print(f"⚠️ خطأ في {symbol}: {e}")
            continue
    return filtered

def run():
    now = datetime.datetime.now(timezone)
    send_message(f"📡 بدأ الفحص: {now.strftime('%H:%M:%S')}")

    stocks = get_filtered_stocks()
    for sym in stocks:
        send_message(f"🚀 سهم بداية انطلاق: {sym}")

if __name__ == "__main__":
    while True:
        run()
        time.sleep(600)

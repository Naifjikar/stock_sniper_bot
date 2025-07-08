import requests
import time
from datetime import datetime
from telegram import Bot

API_KEY = "PDTlX9ib5N6laEnauklHAgoN8UGr12uh"
FINNHUB_URL = "https://finnhub.io/api/v1"

TOKEN = "8085180830:AAFJqSio_7BJ3n_1jbeHvYEZU5FmDJkT_Dw"
CHANNEL_ID = -1002138790851  # قناة صيد الأسهم الخاصة

bot = Bot(token=TOKEN)

def get_filtered_stocks():
    url = f"{FINNHUB_URL}/stock/symbol?exchange=US&token={API_KEY}"
    response = requests.get(url)
    data = response.json()

    filtered = []
    for sym in data:
        try:
            try:
    symbol = sym["symbol"] if isinstance(sym, dict) else sym
    print(f"🔍 فحص السهم: {symbol}")
except Exception as e:
    print(f"🔍 فحص السهم: error - {e}")

            quote_url = f"{FINNHUB_URL}/quote?symbol={symbol}&token={API_KEY}"
            quote = requests.get(quote_url).json()

            current_price = quote.get("c", 0)
            open_price = quote.get("o", 0)
            volume = quote.get("v", 0)

            if (
                0.1 <= current_price <= 1000 and
                current_price > open_price and
                volume > 5_000_000
            ):
                filtered.append(symbol)

        except Exception as e:
            print(f"❌ خطأ في {sym}: {e}")

    return filtered

def send_stock_recommendation(symbol):
    try:
        vwap_url = f"{FINNHUB_URL}/indicator?symbol={symbol}&resolution=3&indicator=vwap&token={API_KEY}"
        vwap_data = requests.get(vwap_url).json()

        vwap_value = vwap_data.get("vwap", [])
        if not vwap_value:
            print(f"🚫 لا يوجد VWAP للسهم: {symbol}")
            return

        entry_price = round(vwap_value[-1], 2)

        targets = [
            round(entry_price + 0.08, 2),
            round(entry_price + 0.15, 2),
            round(entry_price + 0.25, 2),
            round(entry_price + 0.4, 2),
        ]
        stop_loss = round(entry_price - 0.09, 2)

        message = f"""
📊 توصية سهم: {symbol}
دخول: {entry_price}
أهداف: {targets[0]} - {targets[1]} - {targets[2]} - {targets[3]}
وقف الخسارة: {stop_loss}
        """
        bot.send_message(chat_id=CHANNEL_ID, text=message.strip())
        print(f"✅ تم إرسال التوصية للسهم: {symbol}")

    except Exception as e:
        print(f"❌ فشل إرسال توصية {symbol}: {e}")

def run():
    print("🚀 بدأ الفحص في:", datetime.now().strftime("%d-%m-%Y %I:%M:%S %p"))
    symbols = get_filtered_stocks()
    for symbol in symbols[:4]:
        send_stock_recommendation(symbol)

if __name__ == "__main__":
    run()

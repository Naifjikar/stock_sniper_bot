import os
import requests

# قراءة المتغيرات من البيئة
TOKEN = os.getenv("BOT_TOKEN")
PRIVATE_CHANNEL = os.getenv("PRIVATE_CHANNEL")
API_KEY = os.getenv("API_KEY")

def send_msg(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, data=data)

# دالة جلب الأسهم المطابقة للشروط
def fetch_filtered_stocks():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={API_KEY}"
    response = requests.get(url)
    data = response.json()
    filtered = []

    for stock in data.get("tickers", []):
        ticker = stock["ticker"]
        price = stock["lastTrade"]["p"]
        volume = stock["day"]["v"]
        open_price = stock["day"]["o"]
        prev_close = stock["prevDay"]["c"]
        avg_vol = stock["day"]["av"]

        if (
            1 <= price <= 5 and
            volume >= 5_000_000 and
            price > prev_close and
            ((price - open_price) / open_price) * 100 > 10 and
            volume > avg_vol * 5
        ):
            filtered.append({
                "ticker": ticker,
                "price": price,
                "open": open_price,
                "prev_close": prev_close
            })

    return filtered

# توليد توصية برسالة منظمة
def generate_recommendation(stock):
    entry = round(stock["price"], 2)
    targets = [round(entry * (1 + i / 100), 2) for i in [8, 15, 25, 40]]
    stop = round(entry * 0.91, 2)

    return f"""🚨 توصية اليوم 🚨

📉 سهم: {stock['ticker']}
📥 دخول: {entry}
🎯 أهداف:
- {targets[0]}
- {targets[1]}
- {targets[2]}
- {targets[3]}
⛔️ وقف: {stop}

#توصيات_الأسهم"""

# تشغيل البوت
if __name__ == "__main__":
    stocks = fetch_filtered_stocks()
    print(f"Found {len(stocks)} stocks matching filters")

    if not stocks:
        send_msg(PRIVATE_CHANNEL, "📭 لا توجد توصيات مطابقة اليوم.")
    else:
        sent = []
        for stock in stocks:
            if stock["ticker"] not in sent:
                msg = generate_recommendation(stock)
                send_msg(PRIVATE_CHANNEL, msg)
                sent.append(stock["ticker"])

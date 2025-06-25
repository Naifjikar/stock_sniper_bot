import os
import requests
from telegram import Bot

TOKEN = os.getenv("BOT_TOKEN")
PRIVATE_CHANNEL = os.getenv("PRIVATE_CHANNEL")
API_KEY = os.getenv("API_KEY")

bot = Bot(token=TOKEN)

def fetch_filtered_stocks():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={API_KEY}"
    data = requests.get(url).json()
    results = []
    for s in data.get("tickers", []):
        price = s["lastTrade"]["p"]
        if (1 <= price <= 5
            and s["day"]["v"] >= 5_000_000
            and price > s["prevDay"]["c"]
            and ((price - s["day"]["o"]) / s["day"]["o"]) * 100 > 10
            and s["day"]["v"] > s["day"]["av"] * 5):
            results.append(s)
    return results

def generate_recs(stocks):
    msgs = []
    sent = set()
    for s in stocks:
        t = s["ticker"]
        if t in sent: continue
        price = round(s["lastTrade"]["p"], 2)
        targets = [round(price*(1+i/100),2) for i in [8,15,25,40]]
        stop = round(price*0.91,2)
        msgs.append(f"🚨 توصية: {t}\nدخول: {price}\nأهداف: {targets}\nوقف: {stop}")
        sent.add(t)
    return msgs

if __name__ == "__main__":
    st = fetch_filtered_stocks()
    print("Found", len(st), "stocks")
    if not st:
        bot.send_message(chat_id=PRIVATE_CHANNEL, text="📭 لا توجد توصيات اليوم.")
    else:
        for m in generate_recs(st):
            bot.send_message(chat_id=PRIVATE_CHANNEL, text=m)

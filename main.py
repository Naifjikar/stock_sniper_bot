import requests
import datetime
import pytz

# إعدادات البوت
TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'

# الوقت
timezone = pytz.timezone('Asia/Riyadh')
now = datetime.datetime.now(timezone)

# دالة إرسال رسالة
def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHANNEL_ID, 'text': text}
    response = requests.post(url, data=payload)
    print(f"📤 Response: {response.status_code} - {response.text}")

# إرسال الرسالة
send_message(f"📡 بدأ الفحص: {now.strftime('%H:%M:%S')}")

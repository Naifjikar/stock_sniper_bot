from telegram import Bot

# التوكن ومعرف القناة
TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'

# إنشاء البوت
bot = Bot(token=TOKEN)

# إرسال رسالة واحدة فقط
bot.send_message(chat_id=CHANNEL_ID, text="🚀 بداية انطلاق: $TEST")

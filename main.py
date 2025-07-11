import asyncio
from telegram import Bot

TOKEN = '8085180830:AAGHgsKIdVSFNCQ8acDiL8gaulduXauN2xk'
CHANNEL_ID = '-1002608482349'

bot = Bot(token=TOKEN)

async def main():
    await bot.send_message(chat_id=CHANNEL_ID, text="🚀 بداية انطلاق: $TEST")

# تشغيل الكود
asyncio.run(main())

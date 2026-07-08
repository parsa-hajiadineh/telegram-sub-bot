from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

user_states = {}
_last_bot_messages = {}

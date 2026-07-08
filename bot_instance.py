from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from state_store import user_states

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

_last_bot_messages = {}

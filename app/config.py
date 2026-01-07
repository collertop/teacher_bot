import os
from dotenv import load_dotenv 

load_dotenv() #«Прочитаю файл .env и загружу переменные в память процесса»

BOT_TOKEN = os.getenv("BOT_TOKEN") #достаёт значение по имени
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY") 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ADMIN_IDS = {int(x.strip()) for x in (os.getenv("ADMIN_IDS") or "").split(",") if x.strip().isdigit()}


if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing in .env") #чтобы бот не стартовал “пустым” и не падал потом непонятно где


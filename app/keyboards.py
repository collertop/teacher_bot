from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✍️ Новое задание")],
        [KeyboardButton(text="📌 Что я умею"), KeyboardButton(text="📷 Решить по фото")],
        [KeyboardButton(text="💳 Лимиты")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Напиши задачу или выбери кнопку 👇",
)

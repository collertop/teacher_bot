import asyncio

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import StateFilter

from app.keyboards import MAIN_KB
from app.limits import check_and_hit, peek_limits, LIMIT_EXHAUSTED_MSG
from app.services import ask_teacher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from urllib.parse import quote
from app.config import ADMIN_IDS

from app.vision import extract_task_from_photo_gemini
from aiogram.enums import ChatAction


from app.db import (
    ensure_user,
    touch_user,
    apply_referral,
    add_credits,
    get_credits,
    set_credits,
    stats_24h,
    get_user_card,
    count_referrals,
    get_all_user_ids,
)



router = Router() #это “папка с правилами”: какие сообщения куда отправлять
class TaskFlow(StatesGroup):
    waiting_task = State()
class BroadcastFlow(StatesGroup):
    waiting_content = State()
    waiting_confirm = State()
  


@router.message(Command("start"))
async def start_handler(message: Message):
    args = message.text.split(maxsplit=1)
    ref_id = args[1].strip() if len(args) > 1 else None

    # ⬇️ ВАЖНО: теперь сохраняем и получаем is_new
    is_new = await ensure_user(
        message.from_user.id,
        message.from_user.username
    )
    await touch_user(message.from_user.id)

    # ⬇️ РЕФЕРАЛКА ТОЛЬКО ЕСЛИ ЮЗЕР НОВЫЙ
    if is_new and ref_id and ref_id.isdigit():
        inviter_id = int(ref_id)
        invitee_id = message.from_user.id

        if inviter_id != invitee_id:
            await ensure_user(inviter_id)

            ok = await apply_referral(inviter_id, invitee_id)
            if ok:
                await add_credits(inviter_id, 5)

                invited = await count_referrals(inviter_id)
                progress = f"{invited} / 15"
                extra = "\n\n🔥 Ты в розыгрыше iPhone 17!" if invited >= 15 else ""

                try:
                    uname = message.from_user.username
                    who = f"@{uname}" if uname else f"id:{invitee_id}"
                    await message.bot.send_message(
                        inviter_id,
                        f"🎉 Новый реферал!\n"
                        f"👤 Друг: {who}\n"
                        f"✅ Начислено +5 ответов 🎁\n"
                        f"📱 Прогресс iPhone 17: {progress}"
                        f"{extra}"
                    )
                except TelegramForbiddenError:
                    pass

    # 👇 1) Приветствие с кнопкой поддержки (inline)
    support_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💬 Условия конкурса",
            url="https://t.me/reshebnik_gdz_ai_onegin"
        )]
    ])

    await message.answer(
        "Привет! Я решебник — Онегин✍️📘\n\n"
        "🤝Твой школьный ИИ-наставник. Помогаю разбирать задачи по шагам.\n\n"
        "📚 Умею решать все предметы, объясняя простыми словами.\n\n"
        "Лайфхаки для лучшего результата:\n"
        "• Делай четкие фото при хорошем свете\n"
        "• Пиши после ответа доп.вопросы, если нужно больше информации\n\n"
        "Нажми НОВОЕ ЗАДАНИЕ — и поехали 👇",
        reply_markup=support_kb,
    )

    # 👇 2) Отдельным сообщением включаем панель с кнопками (MAIN_KB)
    await message.answer(
        "Напиши задачу или выбери кнопку 👇",
        reply_markup=MAIN_KB,
    )




@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer("Напиши задачу текстом, я объясню шаги решения ✅")


@router.message(StateFilter(None), F.photo)
async def solve_from_photo(message: Message):
    user_id = message.from_user.id

    # активность/регистрация
    await touch_user(user_id)
    await ensure_user(user_id, message.from_user.username)

    # 0) мгновенная проверка: если 0 — Gemini не трогаем
    info0 = await peek_limits(user_id)
    if info0["credits"] <= 0:
        return await message.answer(LIMIT_EXHAUSTED_MSG)

    # 1) скачать фото
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    photo_bytes = await message.bot.download_file(file.file_path)

    # ✅ Универсально: если это файл — читаем, если уже bytes — берём как есть
    if hasattr(photo_bytes, "read"):
        data = photo_bytes.read()
    else:
        data = photo_bytes

    # 2) typing + статус
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    await message.answer("🧠 Понял задачу с фото. Решаю…")

    # 3) Gemini OCR: получить ТОЛЬКО текст условия
    try:
        task_text = await extract_task_from_photo_gemini(data)
    except Exception:
        return await message.answer("⛔️ Не получилось прочитать фото. Попробуй другое (четче/ближе).")

    if not task_text:
        return await message.answer("⛔️ Я не увидел текст на фото. Сделай фото ближе и ровнее.")

    # 4) списываем кредит ТОЛЬКО после успешного OCR
    ok, info = await check_and_hit(user_id)
    if not ok:
        return await message.answer(info)

    # 5) решаем через Mistral (ask_teacher)
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    answer = await ask_teacher(task_text)
    await message.answer(answer)

    credits_left = info["credits_left"]
    if credits_left <= 0:
        await message.answer(
            "💳 Ответов больше нет.\n"
            "🎁 Завтра автоматически начислится +2\n\n"
            "🤝 Хочешь продолжить уже сейчас?\n"
            "Пригласи друга — получишь +5 ответов.\n\n"
            "Открой «💳 Лимиты» и забери ссылку."
        )
    else:
        await message.answer(f"💳 Ответов осталось: {credits_left}")





@router.message(F.sticker)
async def sticker_handler(message: Message):
    await message.answer("Стикеры пока не понимаю 🙌 Пришли задачу текстом.")

@router.message(F.animation)
async def gif_handler(message: Message):
    await message.answer("Я пока не понимаю GIF 🙌 Пришли задачу текстом.")    

@router.message(F.voice)
async def voice_handler(message: Message):
    await message.answer("Голосовые пока не поддерживаются 🎤 Пришли задачу текстом.")

@router.message(F.video_note)
async def video_note_handler(message: Message):
    await message.answer("Кружочки пока не понимаю 🎥 Напиши задачу текстом.")
    

BUTTON_TEXTS = {
    "✍️ Новое задание",
    "📌 Что я умею",
    "📷 Решить по фото",
    "💳 Лимиты",
}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

PRIZES = [
    (15, "📱 iPhone 17"),
]




@router.message(TaskFlow.waiting_task, F.text.in_(BUTTON_TEXTS))
async def task_mode_buttons(message: Message, state: FSMContext):
    # В режиме ожидания задачи кнопки не должны тратить кредиты
    if message.text == "💳 Лимиты":
        return await limits_button(message)

    if message.text == "📌 Что я умею":
        return await examples_button(message)

    if message.text == "📷 Решить по фото":
        return await solve_by_photo_button(message)

    if message.text == "✍️ Новое задание":
        # просто повторим инструкцию и останемся в ожидании
        return await ask_task_button(message, state)


@router.message(TaskFlow.waiting_task, F.text & ~F.command & ~F.text.in_(BUTTON_TEXTS))
async def task_text_handler(message: Message, state: FSMContext):
    await touch_user(message.from_user.id)
    await ensure_user(message.from_user.id, message.from_user.username)

    ok, info = await check_and_hit(message.from_user.id)
    if not ok:
        await state.clear()
        return await message.answer(info)

    credits_left = info["credits_left"]

    await message.bot.send_chat_action(message.chat.id, "typing")

    answer = await ask_teacher(message.text)
    await message.answer(answer)

    if credits_left <= 0:
        await message.answer(
            "💳 Ответов больше нет.\n"
            "🎁 Завтра автоматически начислится +2\n\n"
            "🤝 Хочешь продолжить уже сейчас?\n"
            "Пригласи друга — получишь +5 ответов.\n\n"
            "Открой «💳 Лимиты» и забери ссылку."
        )
    else:
        await message.answer(f"💳 Ответов осталось: {credits_left}")

    # выходим из режима задания
    await state.clear()

    

@router.message(F.text == "✍️ Новое задание")
async def ask_task_button(message: Message, state: FSMContext):
    await state.set_state(TaskFlow.waiting_task)
    await message.answer(
        "Ок! Напиши задачу вот так 👇\n\n"
        "📘 Предмет:\n"
        "🎓 Класс:\n"
        "📝 Условие:\n"
        "❓ Что нужно найти:\n\n"
        "Пример:\n"
        "Математика, 7 класс\n"
        "Найди значение выражения ...\n\n"
        "❗️Важно: один запрос = одно упражнение/задание❗️",
    )

@router.message(F.text == "📌 Что я умею")
async def examples_button(message: Message):
    await message.answer(
        "📌 Что я умею\n\n"
        "✍️ Решаю задачи любой сложности\n"
        "📸 Понимаю фото из учебника\n"
        "🎙️ Голосовые сообщения — скоро\n"
        "💡 Пишу сочинения, рефераты и эссе\n"
        "🧮 Работаю с математическими формулами\n\n"
        "🚀 Зачем я здесь\n\n"
        "Помогаю разбираться в учёбе\n"
        "и становиться лучше шаг за шагом\n\n"
        "🤝 Помоги сделать бота лучше\n\n"
        "Если ты нашёл ошибку\n"
        "или хочешь улучшить бота — напиши нам 🙌\n"
        "Каждый отзыв реально читается и учитывается\n\n"
        "💬 Поддержка: @Your_Onegin"
    )


@router.message(F.text == "📷 Решить по фото")
async def solve_by_photo_button(message: Message):
    await message.answer(
        "📷 Пришли фото!\n\n"
    )    

    


@router.message(F.text == "💳 Лимиты")
async def limits_button(message: Message):
    info = await peek_limits(message.from_user.id)

    me = await message.bot.get_me()
    bot_username = me.username
    user_id = message.from_user.id
    ref_link = f"https://t.me/{bot_username}?start={user_id}"

    text = (
        f"💳 Ответов осталось: {info['credits']}\n\n"
        "🆓 Получи прямо сейчас бесплатные ответы за друзей:\n\n"
        "👉 Скопируй ссылку\n"
        "👉 Отправь её своим друзьям и одноклассникам\n"
        "👉👉 Пользуйся решебником БЕСПЛАТНО!\n\n"
        "Твоя ссылка (нажми «Copy» чтобы скопировать):\n"
        f"<pre><code>{ref_link}</code></pre>"
    )

    share_text = "🆓 Забирай бесплатные ответы в решебнике! Жми Start 👇"
    share_url = f"https://t.me/share/url?url={quote(ref_link)}&text={quote(share_text)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 ПОДЕЛИТЬСЯ", url=share_url)]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Нет доступа")
    await message.answer(
        "🛠 Админка:\n"
        "/stats — статистика\n"
        "/give user_id 10 — выдать кредиты\n"
        "/set user_id 10 — установить кредиты\n"
        "/user user_id — карточка юзера\n"
        "/broadcast — рассылка всем\n"
        "/cancel — отмена действия\n"

    )
@router.message(Command("give"))
async def admin_give(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
        return await message.answer("Формат: /give user_id 10")

    uid = int(parts[1])
    delta = int(parts[2])

    await add_credits(uid, delta)
    credits = await get_credits(uid)
    await message.answer(f"✅ Готово. У юзера {uid} теперь {credits} кредитов.")



@router.message(Command("set"))
async def admin_set(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return await message.answer("Формат: /set user_id 10")

    uid = int(parts[1])
    value = int(parts[2])

    await set_credits(uid, value)
    await message.answer(f"✅ Установил {value} кредитов для {uid}.")

@router.message(Command("stats"))
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    s = await stats_24h()
    await message.answer(
        "📊 Статистика за 24ч:\n"
        f"🆕 Новых: {s['new_users']}\n"
        f"🔥 Активных: {s['active_users']}"
    )

@router.message(Command("user"))
async def admin_user(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await message.answer("Формат: /user user_id")

    uid = int(parts[1])

    info = await get_user_card(uid)  # сделаем функцию в db.py
    if not info:
        return await message.answer(f"Юзер {uid} не найден в базе.")

    invited = info["invited_count"]
    progress = f"{invited} / 15"
    extra = "\n🔥 Ты в розыгрыше iPhone 17!" if invited >= 15 else ""

    await message.answer(
        f"👤 Юзер: {uid}\n"
        f"@{info['username'] or '—'}\n"
        f"💳 Кредиты: {info['credits']}\n"
        f"🗓 Зарегистрирован: {info['created_at']}\n"
        f"🔥 Последняя активность: {info['last_active']}\n"
        f"👥 Приглашено: {invited}\n\n"
        f"📊 Прогресс по призам:\n{progress}"
        f"{extra}"
)

@router.message(Command("broadcast"))
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ Нет доступа")

    await state.set_state(BroadcastFlow.waiting_content)
    await message.answer(
        "📣 Рассылка\n\n"
        "Пришли ОДНО сообщение для рассылки всем пользователям:\n"
        "— текст\n"
        "— фото с подписью\n"
        "— gif\n\n"
        "Отмена: /cancel"
    )

@router.message(StateFilter(BroadcastFlow.waiting_content))
async def broadcast_receive(message: Message, state: FSMContext):
    payload = None

    if message.text:
        payload = {"type": "text", "text": message.text}

    elif message.photo:
        payload = {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": message.caption or ""
        }

    elif message.animation:
        payload = {
            "type": "gif",
            "file_id": message.animation.file_id,
            "caption": message.caption or ""
        }

    else:
        return await message.answer("❌ Этот тип сообщения не поддерживается")

    await state.update_data(payload=payload)
    await state.set_state(BroadcastFlow.waiting_confirm)
    await message.answer("✅ Принял. Напиши /send для рассылки или /cancel")

@router.message(Command("send"), StateFilter(BroadcastFlow.waiting_confirm))
async def broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    payload = data.get("payload")
    if not payload:
        await state.clear()
        return await message.answer("❌ Нечего отправлять. Запусти /broadcast заново.")

    user_ids = await get_all_user_ids()
    await message.answer(f"🚀 Начинаю рассылку: {len(user_ids)} пользователям...")

    ok_count = 0
    fail_count = 0

    for uid in user_ids:
        try:
            if payload["type"] == "text":
                await message.bot.send_message(uid, payload["text"])

            elif payload["type"] == "photo":
                await message.bot.send_photo(uid, payload["file_id"], caption=payload["caption"])

            elif payload["type"] == "gif":
                await message.bot.send_animation(uid, payload["file_id"], caption=payload["caption"])

            ok_count += 1
            await asyncio.sleep(0.05)

        except TelegramForbiddenError:
            fail_count += 1

        except TelegramRetryAfter as e:
            await asyncio.sleep(int(e.retry_after) + 1)
            fail_count += 1

        except Exception:
            fail_count += 1

    await state.clear()
    await message.answer(
        "✅ Рассылка завершена.\n"
        f"📬 Успешно: {ok_count}\n"
        f"⚠️ Ошибок: {fail_count}"
    )


@router.message(Command("cancel"))
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Отменено.")


    
@router.message(F.text & ~F.command)
async def text_outside_task(message: Message):
    await touch_user(message.from_user.id)
    await message.answer("Чтобы я решил задачу — нажми «✍️ Новое задание» 🙂")


        
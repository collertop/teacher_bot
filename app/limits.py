from app.db import (
    daily_refill,
    get_credits,
    spend_credit,
)

# Общий текст, когда лимит закончился
LIMIT_EXHAUSTED_MSG = (
    "💳 Ответов больше нет.\n"
    "🎁 Завтра автоматически начислится +2\n\n"
    "🤝 Хочешь продолжить уже сейчас?\n"
    "Пригласи друга — получишь +5 ответов.\n\n"
    "Открой «💳 Лимиты» и забери ссылку."
)


async def check_and_hit(user_id: int):
    """
    Проверка и списание кредита.
    1) начисляем ежедневные +2 (если нужно)
    2) проверяем, есть ли кредиты
    3) списываем 1 кредит
    """
    # ежедневное начисление
    await daily_refill(user_id, per_day=2)

    credits = await get_credits(user_id)
    if credits <= 0:
        return False, LIMIT_EXHAUSTED_MSG

    ok = await spend_credit(user_id, 1)
    if not ok:
        return False, LIMIT_EXHAUSTED_MSG

    credits_left = await get_credits(user_id)
    return True, {"credits_left": credits_left}


async def peek_limits(user_id: int) -> dict:
    """
    Просто показать, сколько кредитов осталось
    """
    await daily_refill(user_id, per_day=2)
    credits = await get_credits(user_id)
    return {"credits": credits}

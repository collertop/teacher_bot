import os
import asyncio
from io import BytesIO
from PIL import Image
from google import genai

MODEL_OCR = "gemini-2.5-flash"
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

OCR_PROMPT = (
    "Считай текст с изображения школьного задания.\n"
    "Верни ТОЛЬКО условие задачи, без решения.\n"
    "Если есть варианты ответов — включи их.\n"
    "Если задач несколько — верни первую сверху.\n"
    "Сохраняй формулы текстом: x^2, (a+b)/c, sqrt(5).\n"
)

def _prepare_image(photo_bytes: bytes) -> Image.Image:
    img = Image.open(BytesIO(photo_bytes)).convert("RGB")

    # нормализация: уменьшаем, чтобы было стабильнее и дешевле
    max_side = 1600
    w, h = img.size
    scale = max(w, h) / max_side
    if scale > 1:
        img = img.resize((int(w / scale), int(h / scale)))

    return img

async def extract_task_from_photo_gemini(photo_bytes: bytes) -> str:
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is empty")

    img = _prepare_image(photo_bytes)

    # google-genai синхронный внутри → уносим в thread
    resp = await asyncio.to_thread(
        client.models.generate_content,
        model=MODEL_OCR,
        contents=[OCR_PROMPT, img],
    )

    return (getattr(resp, "text", "") or "").strip()

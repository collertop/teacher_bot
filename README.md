# teacher_bot

AI-powered Telegram bot that helps students solve educational tasks.
Completely free!
---

## 🚀 Features

- Text-based problem solving
- Photo-based problem solving
- Token limit system
- Referral bonus system

---

## 🧠 Architecture

Photo → Gemini (vision) → Extracted text → Mistral (reasoning) → Telegram response  

Text → Mistral → Telegram response

This design minimizes Gemini token usage and keeps the bot cost-efficient.

---

## 🛠 Tech Stack

- Python
- Telegram Bot API
- Gemini API (vision)
- Mistral (reasoning)
- SQLite (local storage)

---

## 📦 Dependencies

The project requires the following Python packages:

- python-telegram-bot
- google-generativeai
- mistralai
- python-dotenv
- sqlite3 (built-in)

Install dependencies:

```bash
pip install -r requirements.txt


## ▶ Run (local)

1. Create virtual environment  
2. Install dependencies  
3. Configure `.env`  
4. Run `main.py`

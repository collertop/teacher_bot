# teacher_bot

AI-powered Telegram bot that helps students solve educational tasks via text and photos.

---

## 🚀 Features

- Solve tasks with plain text
- Solve tasks from photos (vision + reasoning)
- Daily token limit and notification
- Minimal vision token usage for cost-efficiency

---

## 🧠 Architecture

**Text flow**  
Text → Mistral → Telegram response

**Photo flow**  
Photo → Gemini (vision) → Extracted text → Mistral → Telegram response

Gemini is used only for vision (OCR).  
Mistral handles reasoning and answers.

---

## 🛠 Tech Stack

- Python 3.10+
- `python-telegram-bot`
- `google-generativeai` (Gemini)
- `mistralai` (Mistral)
- `python-dotenv`
- `SQLite` (built-in)

---

## 📦 Installation (local)

### 1) Create and activate virtual environment

**macOS / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows**
```bash
python -m venv venv
venv\Scripts\activate
```

### 2) Install dependencies
```bash
pip install -r requirements.txt
```
If requirements.txt is missing, install manually:
```bash
pip install python-telegram-bot google-generativeai mistralai python-dotenv
```

## 🔐 Configuration (.env)
Create a .env file in the project root:
```bash
BOT_TOKEN=your_telegram_bot_token
MISTRAL_API_KEY=your_mistral_api_key
GEMINI_API_KEY=your_gemini_api_key
ADMIN_IDS=123456789,987654321
```
#Notes:
```bash

BOT_TOKEN is required
MISTRAL_API_KEY is required for solving tasks
GEMINI_API_KEY is required for photo solving
ADMIN_IDS is optional (comma-separated Telegram user IDs)
```

##▶ Run the bot
```bash
python main.py
```

##📁 Project Structure
 main.py — application entry point
 app/config.py — environment configuration
 app/handlers.py — Telegram message handlers
 app/services.py — Mistral integration and business logic
 app/vision.py — Gemini photo text extraction
 app/limits.py — daily token limit logic
 app/db.py — SQLite database logic


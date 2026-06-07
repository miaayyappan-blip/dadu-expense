# 🤖 dadu-expense

> AI-powered expense tracker — voice entry, receipt scanning, smart assistant

Built for a 72-hour hackathon. Tracks expenses using your voice, receipt photos,
or manual entry. Includes an AI assistant that answers questions about your spending.

---

## ✨ Features

| Feature | How it works |
|---|---|
| 🎤 Voice Entry | Speak → OpenAI Whisper transcribes → Gemini extracts fields |
| 📸 Receipt Scan | Photo → PaddleOCR reads text → Gemini parses receipt structure |
| 💬 AI Assistant | "How much on food?" → Intent classification → Safe DB query → Natural answer |
| 📊 Dashboard | Spending trends, category breakdown, budget alerts |
| 💰 Budget Tracking | Set category limits, 80%/100% warnings, progress bars |

## 🧱 Tech Stack

**Backend:** FastAPI · PostgreSQL · SQLAlchemy (async) · Alembic · JWT Auth

**Frontend:** React · Vite · TypeScript · Tailwind CSS · Recharts

**AI:** OpenAI Whisper · Google Gemini 1.5 Flash · PaddleOCR

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- Docker Desktop
- OpenAI API key
- Google AI Studio (Gemini) API key

### 1. Clone and configure
```bash
git clone https://github.com/YOUR_USERNAME/dadu-expense.git
cd dadu-expense

cp backend/.env.example backend/.env
# Edit backend/.env and fill in your API keys
```

### 2. Start the database
```bash
docker compose up postgres -d
```

### 3. Start the backend
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create database tables
python -c "
import asyncio
from app.database.session import engine, Base
import app.models
async def create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Done!')
asyncio.run(create())
"

uvicorn app.main:app --reload --port 8000
```

### 4. Start the frontend
```bash
# New terminal
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** — sign up and start tracking!

API docs: **http://localhost:8000/docs**

---

## 🐳 Docker (run everything at once)
```bash
# Fill in backend/.env first
docker compose up --build
```

---

## 📁 Project Structure

```
dadu-expense/
├── backend/
│   └── app/
│       ├── ai/              # Whisper, PaddleOCR, Gemini, Assistant
│       ├── api/v1/          # HTTP endpoints
│       ├── models/          # Database tables
│       ├── schemas/         # Request/response shapes
│       └── services/        # Business logic
└── frontend/
    └── src/
        ├── api/             # Axios + all API calls
        ├── pages/           # Dashboard, Expenses, Add, Budgets, Login
        └── components/      # Sidebar, Navbar, UI components
```

---

## 🔐 Environment Variables

```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dadu_expense
SECRET_KEY=your-32-character-secret-key
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
CORS_ORIGINS=http://localhost:3000
```

---

## 🏗️ Architecture Decisions

**Why two AI models for voice?**
Whisper handles speech-to-text (what it's best at). Gemini handles semantic extraction (what LLMs are best at). Combining them beats using one model for both.

**Why no SQL generation in the assistant?**
LLMs generating SQL is a security risk — they hallucinate table names and can bypass row-level security. Instead: LLM classifies intent → maps to a pre-written parameterized query template.

**Why deterministic confidence scoring?**
LLMs invent confidence numbers. Our scorer computes it from verifiable signals: field presence, amount range, date validity. You can audit and trust the number.

---

## 📄 License
MIT

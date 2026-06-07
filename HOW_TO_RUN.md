# How to Fix Your GitHub Repo + Run the App
# ============================================
# Your current problem: all files are flat in the root.
# This guide fixes that in 3 steps.

# ════════════════════════════════════════════
# STEP 1 — Download your repo to your computer
# ════════════════════════════════════════════

# Open a terminal (Mac: press Cmd+Space, type "Terminal")
# (Windows: press Win key, type "PowerShell")

# Navigate to where you want the project:
cd Desktop

# Download your repo:
git clone https://github.com/YOUR_USERNAME/dadu-expense.git
cd dadu-expense

# You'll see all the flat files here. That's okay — we'll fix it next.


# ════════════════════════════════════════════
# STEP 2 — Run the reorganize script
# ════════════════════════════════════════════

# The reorganize.py script moves every file to its correct folder.
# Download it from the repo first (it should already be there if you followed along)
# then run:

python3 reorganize.py

# You'll see output like:
#   ✅ Moved 35 files:
#     main.py → backend/app/main.py
#     security.py → backend/app/core/security.py
#     ...

# After this, your folder structure will look correct.
# Verify it with:
find . -type f | grep -v .git | grep -v node_modules | sort


# ════════════════════════════════════════════
# STEP 3 — Create your .env file
# ════════════════════════════════════════════

cp backend/.env.example backend/.env

# Open backend/.env in any text editor and fill in:
#
#   DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dadu_expense
#   SECRET_KEY=          ← generate one (see below)
#   GEMINI_API_KEY=      ← paste your Gemini key here
#   OPENAI_API_KEY=      ← leave BLANK (not needed, Gemini handles voice)

# To generate a SECRET_KEY, run this:
python3 -c "import secrets; print(secrets.token_hex(32))"
# Copy the output and paste it as SECRET_KEY in your .env


# ════════════════════════════════════════════
# STEP 4 — Switch voice to Gemini (no OpenAI needed)
# ════════════════════════════════════════════

# Since you don't have OpenAI billing, replace the Whisper service
# with the Gemini version:

cp backend/app/ai/speech/whisper_service_gemini.py \
   backend/app/ai/speech/whisper_service.py

# This drops in a version that uses your Gemini key for transcription.
# Everything else in the pipeline stays exactly the same.


# ════════════════════════════════════════════
# STEP 5 — Install Docker and start the database
# ════════════════════════════════════════════

# Install Docker Desktop if you haven't:
# https://www.docker.com/products/docker-desktop
# (It's free. Just download and install like any app.)

# Once Docker is open/running, start the database:
docker compose up postgres -d

# Wait 5 seconds, then check it's running:
docker compose ps
# Should show: dadu-expense-postgres-1    running (healthy)


# ════════════════════════════════════════════
# STEP 6 — Run the backend
# ════════════════════════════════════════════

cd backend

# Create a Python virtual environment (isolated sandbox for packages):
python3 -m venv venv

# Activate it:
# Mac/Linux:
source venv/bin/activate
# Windows PowerShell:
# .\venv\Scripts\Activate.ps1

# Install all Python packages:
pip install -r requirements.txt
# This takes 3-5 minutes (PaddleOCR is large, ~500MB)

# Create database tables:
python3 -c "
import asyncio
from app.database.session import engine, Base
import app.models
async def go():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Tables created!')
asyncio.run(go())
"

# Start the server:
uvicorn app.main:app --reload --port 8000

# You should see:
#   INFO:     Uvicorn running on http://0.0.0.0:8000
# Open http://localhost:8000/docs to verify it works.

cd ..


# ════════════════════════════════════════════
# STEP 7 — Run the frontend
# ════════════════════════════════════════════

# Open a NEW terminal tab (keep the backend running in the other one)
cd dadu-expense/frontend

npm install
# Takes 1-2 minutes

npm run dev
# Open http://localhost:3000


# ════════════════════════════════════════════
# STEP 8 — Push the fixed structure to GitHub
# ════════════════════════════════════════════

# From the dadu-expense root folder:
git add .
git commit -m "Fix: proper folder structure + Gemini voice transcription"
git push

# Your GitHub repo will now show folders instead of flat files.


# ════════════════════════════════════════════
# WHAT YOUR REPO SHOULD LOOK LIKE AFTER
# ════════════════════════════════════════════
#
# dadu-expense/
# ├── .gitignore
# ├── README.md
# ├── docker-compose.yml
# ├── reorganize.py
# ├── backend/
# │   ├── requirements.txt
# │   ├── .env.example          ← yes, commit this (no real secrets inside)
# │   └── app/
# │       ├── main.py
# │       ├── core/
# │       │   ├── config.py
# │       │   ├── security.py
# │       │   └── dependencies.py
# │       ├── models/
# │       ├── schemas/
# │       ├── services/
# │       ├── api/v1/endpoints/
# │       └── ai/
# └── frontend/
#     ├── package.json
#     └── src/
#         ├── App.tsx
#         ├── pages/
#         ├── components/
#         └── ...
#
# NOTE: backend/.env is in .gitignore — never commit it!
# NOTE: backend/venv/ is in .gitignore — never commit it!
# NOTE: frontend/node_modules/ is in .gitignore — never commit it!

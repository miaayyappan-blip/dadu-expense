# dadu-expense

An AI-powered expense tracking application that helps users record, organize, and understand their spending through voice input, receipt scanning, and natural language queries.


---

## Overview
dadu-expense reduces that friction by allowing users to:

* Add expenses through voice commands
* Scan receipts and automatically extract purchase details
* Track budgets across categories
* View spending trends and analytics
* Ask questions about their finances using natural language

The goal is to make expense tracking fast enough that users actually continue using it.

---

## Key Features

### Voice-Based Expense Entry

Users can record expenses by speaking naturally.

Example:

> "Spent 450 rupees on lunch today."

The application transcribes the audio and extracts structured expense information automatically.

### Receipt Scanning

Users can upload receipt images and receive extracted information such as:

* Merchant name
* Amount
* Date
* Expense category
* Purchase description

The system combines OCR, preprocessing, rule-based extraction, and LLM-assisted parsing to improve accuracy.

### AI Financial Assistant

Users can ask questions such as:

* How much did I spend on food this month?
* What was my largest expense last week?
* Show spending trends for transportation.

The assistant converts requests into safe application queries and returns natural-language responses.

### Budget Management

Users can create category budgets and monitor progress throughout the month.

The dashboard highlights categories that are approaching or exceeding their limits.

### Analytics Dashboard

Interactive charts provide insights into:

* Spending by category
* Monthly trends
* Budget utilization
* Recent transactions

---

## Technology Stack

### Backend

* FastAPI
* PostgreSQL
* SQLAlchemy (Async)
* JWT Authentication

### Frontend

* React
* TypeScript
* Vite
* Tailwind CSS
* Recharts

### AI Components

* Google Gemini
* EasyOCR
* Custom OCR preprocessing pipeline

---

## System Architecture

### Expense Entry Flow

Voice Input → Whisper → Gemini Extraction → Validation → Database

### Receipt Processing Flow

Receipt Image → Image Preprocessing → OCR → Structured Extraction → Validation → Database

### AI Assistant Flow

User Query → Intent Classification → Safe Query Layer → Response Generation

---

## Running the Project

### Prerequisites

* Python 3.11+
* Node.js 20+
* OpenAI API Key
* Google Gemini API Key

### Backend

```bash
cd backend

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend

npm install
npm run dev
```

Frontend:

```text
http://localhost:3000
```

Backend API:

```text
http://localhost:8000
```

API Documentation:

```text
http://localhost:8000/docs
```

---

## Challenges Addressed

### Receipt OCR Reliability

Receipt images frequently contain:

* Poor lighting
* Skewed angles
* Blurry text
* Thermal paper fading

A preprocessing pipeline was implemented to improve OCR performance before extraction.

### Structured Data Extraction

Receipts vary significantly in layout and formatting.

The extraction system combines deterministic parsing with LLM-based reasoning to improve robustness across different receipt styles.

### Safe Financial Queries

Instead of allowing unrestricted AI-generated database queries, the assistant maps user requests to predefined query patterns to maintain security and consistency.

---

## Current Limitations

* OCR accuracy can vary for low-quality receipt images.
* Some receipt formats require manual review.
* Currency symbols and OCR artifacts may occasionally affect amount extraction.
* Further OCR model improvements are planned.

---

## Future Improvements

* Multi-currency support
* Shared family budgets
* Bank statement import
* Recurring expense detection
* Mobile application
* Improved OCR accuracy using dedicated receipt models

---


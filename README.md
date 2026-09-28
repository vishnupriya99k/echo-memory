# EchoMemory

A conversational memory companion for people with Alzheimer's. The patient asks simple questions ("Who are my grandchildren?") and gets short, gentle answers based only on a family record kept by a caregiver. A separate caregiver dashboard shows conversations, mood, and anything worth checking.

> **Status: prototype.** 

## Features

**Patient app**
- Chat about family members and relationships, by typing or voice
- Family photos shown on request ("show me Sivapriya")
- Reminders for medication, meals, and water, with a gentle re-check if the patient says they forgot
- Mood tracking and repeated-question detection, so replies stay patient and warm

**Caregiver dashboard**
- Daily conversation history and mood summary
- Flagged notes (possibly missed reminders, wellbeing concerns)
- Review queue for new people or facts the patient mentions. Confirmed facts are added to `family_memories.txt`

## Tech Stack

- **Backend:** Python, FastAPI, SQLite
- **AI:** Google Gemini via LangChain
- **Frontend:** HTML, CSS, JavaScript (no framework)

## Project Structure

```
echo-memory/
├── backend/     # API, AI logic, reminders, mood tracking, database
├── frontend/    # Patient app and caregiver dashboard
└── data/        # family_memories.txt, reminders, photos, requirements.txt
```

## Getting Started

Requires Python 3.10+ and a Google Gemini API key.

```bash
# Install
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r data/requirements.txt

# Configure: create a .env file in the project root
GOOGLE_API_KEY=your-key-here
CAREGIVER_USER=caregiver
CAREGIVER_PASS=choose-a-password

# Add family facts to data/family_memories.txt (first line: "The user is <Name>")

# Run
uvicorn backend.api:app --reload --port 8000
```

- Patient app: `http://localhost:8000/`
- Caregiver dashboard: `http://localhost:8000/dashboard`

**Example `family_memories.txt`**
```
-The user is Saraswati a women
- User's children: Meera (daughter), Suresh (son), Radha (daughter), Lakshmi (daughter).
- Meera's children: Arjun (son), Priya (daughter).

```

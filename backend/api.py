"""
api.py — REST API for EchoMemory Companion

"""
import os
import sys
import secrets
import io
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from PIL import Image, ImageOps
import bcrypt

sys.path.append(str(Path(__file__).parent.parent))
from backend.brain import EchoBrain
import backend.db as db

logger = logging.getLogger("echomemory")

ROOT = Path(__file__).parent.parent
FRONTEND_DIR = ROOT / "frontend"
PHOTOS_DIR = ROOT / "data" / "photos"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True) 

app = FastAPI(title="EchoMemory API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["*"],
    allow_headers=["*"],
)

#  Caregiver auth (protects /dashboard and /api/caregiver/*) 
security = HTTPBasic()
CAREGIVER_USER = os.getenv("CAREGIVER_USER", "caregiver")
CAREGIVER_PASS_HASH = os.getenv("CAREGIVER_PASS_HASH")

if not CAREGIVER_PASS_HASH:
   
    CAREGIVER_PASS_HASH = bcrypt.hashpw(b"changeme", bcrypt.gensalt()).decode()
    logger.warning(
        "CAREGIVER_PASS_HASH not set in .env — falling back to the default password "
        "'changeme'. Generate a real one with: python backend/generate_password_hash.py"
    )


def require_caregiver(credentials: HTTPBasicCredentials = Depends(security)):
    valid_user = secrets.compare_digest(credentials.username, CAREGIVER_USER)
    try:
        valid_pass = bcrypt.checkpw(credentials.password.encode("utf-8"), CAREGIVER_PASS_HASH.encode("utf-8"))
    except ValueError:
        logger.error("CAREGIVER_PASS_HASH in .env is not a valid bcrypt hash — regenerate it with generate_password_hash.py")
        valid_pass = False
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=401,
            detail="Incorrect caregiver username or password.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
#  Shared brain instance 
echo = EchoBrain()
memory_loaded = False


@app.on_event("startup")
def load_memory():
    global memory_loaded
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    try:
        with open(ROOT / "data" / "family_memories.txt", "r", encoding="utf-8") as f:
            content = f.read()
        echo.initialize_memory(content)
        memory_loaded = True
    except FileNotFoundError:
        memory_loaded = False


#  Schemas 
class AskRequest(BaseModel):
    question: str


class ReminderRequest(BaseModel):
    label: str
    type: str
    time: str
    days: list[str] | None = None
    notes: str = ""


class SessionNoteRequest(BaseModel):
    note_type: str
    note: str


#  Status 
@app.get("/api/status")
def get_status():
    return {"memory_loaded": memory_loaded, "patient_name": echo.patient_name}


#  Chat 
@app.post("/api/ask")
def ask(req: AskRequest):
    result = echo.ask(req.question)
    return result


#  Reminders 
@app.get("/api/reminders/today")
def reminders_today():
    return echo.reminders.get_todays_reminders()


@app.get("/api/reminders")
def reminders_all():
    return echo.reminders.get_all()


@app.get("/api/reminders/due")
def reminders_due():
    return {"alert": echo.reminders.format_due_alert()}


@app.post("/api/reminders")
def reminders_add(req: ReminderRequest):
    if not req.label.strip() or not req.time.strip():
        raise HTTPException(400, "Label and time are required.")
    return echo.reminders.add_reminder(
        req.label.strip(), req.type, req.time.strip(),
        days=req.days, notes=req.notes.strip(),
    )


@app.delete("/api/reminders/{reminder_id}")
def reminders_delete(reminder_id: int):
    ok = echo.reminders.delete_reminder(reminder_id)
    if not ok:
        raise HTTPException(404, "Reminder not found.")
    return {"deleted": True}


@app.post("/api/reminders/{reminder_id}/done")
def reminders_mark_done(reminder_id: int):
    ok = echo.reminders.mark_done(reminder_id)
    if not ok:
        raise HTTPException(404, "Reminder not found.")
    return {"done": True}


@app.get("/api/mood/summary")
def mood_summary():
    return echo.get_mood_summary()


@app.get("/api/repeated")
def repeated_questions():
    return echo.get_repeated_questions()


@app.post("/api/session/save")
def session_save():
    echo.save_session()
    return {"saved": True}


@app.post("/api/session/note")
def session_note(req: SessionNoteRequest):
    """Called live from the frontend whenever it flags something (missed
    reminder, new info, wellbeing concern) — persisted immediately instead
    of only living in the browser until someone remembers to save."""
    db.add_session_note(req.note_type, req.note)
    return {"saved": True}


#  Photos 
@app.post("/api/photo")
async def add_photo(name: str = Form(...), file: UploadFile = None):
    if not file or not name.strip():
        raise HTTPException(400, "Photo and name are required.")
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    dest = PHOTOS_DIR / f"{name.strip()}.jpg"
    with open(dest, "wb") as f:
        f.write(await file.read())
    with open(ROOT / "data" / "family_memories.txt", "a", encoding="utf-8") as f:
        f.write(f"\n- {name.strip()}'s photo is saved.")
    return {"saved": True, "name": name.strip()}


#  Caregiver dashboard API 
@app.get("/api/caregiver/dates")
def caregiver_dates(user: str = Depends(require_caregiver)):
    return {"dates": db.get_chat_dates()}


@app.get("/api/caregiver/chat")
def caregiver_chat(date: str | None = None, user: str = Depends(require_caregiver)):
    return db.get_chat_history(date)


@app.get("/api/caregiver/notes")
def caregiver_notes(date: str | None = None, user: str = Depends(require_caregiver)):
    return db.get_session_notes(date)


@app.get("/api/caregiver/facts")
def caregiver_facts(user: str = Depends(require_caregiver)):
    return db.get_learned_facts()


@app.post("/api/caregiver/facts/{fact_id}/verify")
def caregiver_verify_fact(fact_id: int, user: str = Depends(require_caregiver)):
    db.set_fact_status(fact_id, 1)
    return {"verified": True}


@app.post("/api/caregiver/facts/{fact_id}/reject")
def caregiver_reject_fact(fact_id: int, user: str = Depends(require_caregiver)):
    db.set_fact_status(fact_id, -1)
    return {"rejected": True}


@app.get("/api/caregiver/mood")
def caregiver_mood(user: str = Depends(require_caregiver)):
    return echo.get_mood_summary()


@app.get("/dashboard")
def dashboard(user: str = Depends(require_caregiver)):
    return FileResponse(str(FRONTEND_DIR / "dashboard.html"))


#  Serve the frontend 
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
app.mount("/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

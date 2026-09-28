"""
SQLite persistence for EchoMemory.

Three tables:
  chat_messages   — every question/answer, permanently logged
  learned_facts   — things the patient said that looked like new info.
                    Stored with verified=0 until a caregiver confirms them
                    on the dashboard; the AI hedges on unverified facts.
  session_notes   — missed-reminder / wellbeing / new-info flags, sent to
                    the server live so a caregiver doesn't depend on someone
                    remembering to click "Save Session" and keep the file.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "echomemory.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,          -- 'user' or 'assistant'
                content TEXT NOT NULL,
                mood TEXT,
                created_at TEXT NOT NULL,
                session_date TEXT NOT NULL   -- YYYY-MM-DD, for easy day lookup
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_name TEXT NOT NULL,
                source_question TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,   -- 0 = unverified, 1 = confirmed, -1 = rejected
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_type TEXT NOT NULL,   -- 'missed_reminder' | 'new_info' | 'wellbeing'
                note TEXT NOT NULL,
                created_at TEXT NOT NULL,
                session_date TEXT NOT NULL
            )
        """)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


#  Chat messages 
def log_message(role: str, content: str, mood: str | None = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_messages (role, content, mood, created_at, session_date) VALUES (?, ?, ?, ?, ?)",
            (role, content, mood, datetime.now().isoformat(), _today()),
        )


def get_chat_history(session_date: str | None = None) -> list[dict]:
    session_date = session_date or _today()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, mood, created_at FROM chat_messages WHERE session_date = ? ORDER BY id",
            (session_date,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_chat_dates() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT session_date FROM chat_messages ORDER BY session_date DESC"
        ).fetchall()
        return [r["session_date"] for r in rows]


#  Learned facts 
def add_learned_fact(fact_name: str, source_question: str):
    with get_conn() as conn:
        # avoid duplicate pending entries for the same name
        existing = conn.execute(
            "SELECT id FROM learned_facts WHERE fact_name = ? AND verified = 0", (fact_name,)
        ).fetchone()
        if existing:
            return
        conn.execute(
            "INSERT INTO learned_facts (fact_name, source_question, verified, created_at) VALUES (?, ?, 0, ?)",
            (fact_name, source_question, datetime.now().isoformat()),
        )


def get_learned_facts(verified: int | None = None) -> list[dict]:
    with get_conn() as conn:
        if verified is None:
            rows = conn.execute("SELECT * FROM learned_facts ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM learned_facts WHERE verified = ? ORDER BY id DESC", (verified,)
            ).fetchall()
        return [dict(r) for r in rows]


def set_fact_status(fact_id: int, verified: int):
    with get_conn() as conn:
        conn.execute("UPDATE learned_facts SET verified = ? WHERE id = ?", (verified, fact_id))


def get_context_facts_text() -> str:
    """Facts to inject into the LLM prompt: confirmed facts stated plainly,
    unverified facts stated with an explicit hedge."""
    facts = get_learned_facts()
    if not facts:
        return ""
    lines = []
    for f in facts:
        if f["verified"] == 1:
            lines.append(f"- {f['fact_name']} was mentioned by the patient and confirmed by a caregiver.")
        elif f["verified"] == 0:
            lines.append(
                f"- The patient mentioned \"{f['fact_name']}\" (from: \"{f['source_question']}\"), "
                f"but this has NOT been confirmed by a caregiver yet. Treat it gently and don't "
                f"state it as certain fact."
            )
    return "\n".join(lines)


def known_fact_names() -> set[str]:
    return {f["fact_name"].lower() for f in get_learned_facts() if f["verified"] != -1}


#  Session notes 
def add_session_note(note_type: str, note: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO session_notes (note_type, note, created_at, session_date) VALUES (?, ?, ?, ?)",
            (note_type, note, datetime.now().isoformat(), _today()),
        )


def get_session_notes(session_date: str | None = None) -> list[dict]:
    session_date = session_date or _today()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM session_notes WHERE session_date = ? ORDER BY id", (session_date,)
        ).fetchall()
        return [dict(r) for r in rows]

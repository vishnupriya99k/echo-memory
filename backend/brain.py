import re
import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sentinel import Sentinel
from sentiment import SentimentTracker, MOOD_EMOJI
from reminders import ReminderManager
import db as db
import logging

logger = logging.getLogger("echomemory")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
PHOTOS_DIR = Path(__file__).parent.parent / "data" / "photos"

_PHOTO_TRIGGER_RE = re.compile(
    r"\b(show me|show|see|picture of|pic of|photo of|what does .* look like|look like)\b", re.I
)

#  System prompt 
SYSTEM_PROMPT = """
You are Kuttymani, a warm and patient memory companion for an elderly person with Alzheimer's.
You speak gently, like a trusted friend who knows the family well.

YOUR RULES:
1. Answer ONLY from the FAMILY FACTS and TODAY'S REMINDERS provided. Never guess.
2. Find the exact fact and state it warmly in ONE short sentence.
3. If the answer is not in the facts say: "I don't seem to have that information, but maybe a family member can remind us!"
4. If the user seems confused or upset, respond with comfort first, then the fact.
5. Use the person's name (from facts) when greeting or comforting them.
6. For vague questions like "who loves me?" or "tell me about my family", give a warm 2-3 sentence summary.
7. NEVER say "based on the facts" or "according to the data" — speak naturally.
8. Remember what was said earlier in this conversation and refer back to it naturally.
9. If the question starts with a reassurance phrase, keep that warm tone throughout.
10. If the patient seems DISTRESSED or LONELY, prioritize comfort over information.
11. For questions like "what do I need to do today?" or "what are my reminders?",
    summarize TODAY'S REMINDERS warmly and clearly.
12. If a reminder is due, gently remind the patient in a caring way.

FAMILY FACTS:
{context}

RECENTLY LEARNED FROM CONVERSATION (some unconfirmed — see notes below):
{learned_facts}

{reminders}

13. For any fact marked "NOT been confirmed by a caregiver yet", speak gently and
    provisionally (e.g. "I think you mentioned...") rather than stating it as certain.
"""


#  Relationship deriver 
def derive_relationships(raw_text: str) -> str:
    parent_to_children: dict[str, list[tuple[str, str]]] = {}
    child_to_parent: dict[str, str] = {}
    gender_map: dict[str, str] = {}
    extra_facts: list[str] = []

    for line in raw_text.strip().splitlines():
        line = line.strip().lstrip("-").strip()
        if not line:
            continue
        line_lower = line.lower()

        m = re.match(r"the user is (\w+)", line, re.I)
        if m:
            name = m.group(1)
            extra_facts.append(f"The User's name is {name}.")
            extra_facts.append(f"The User is a woman named {name}.")
            continue

        m = re.match(r"user'?s?\s+children\s*[:\-]\s*(.+)", line, re.I)
        if m:
            entries = re.findall(r"(\w+)\s*\(\s*(\w+)\s*\)", m.group(1))
            parent_to_children["User"] = entries
            for name, gender in entries:
                child_to_parent[name] = "User"
                gender_map[name] = gender
            continue

        m = re.match(r"(\w+)'s\s+children\s*[:\-]\s*(.+)", line, re.I)
        if m:
            parent = m.group(1)
            entries = re.findall(r"(\w+)\s*\(\s*(\w+)\s*\)", m.group(2))
            parent_to_children[parent] = entries
            for name, gender in entries:
                child_to_parent[name] = parent
                gender_map[name] = gender
            continue

        if "is married to" in line_lower:
            parts = line.split("is married to")
            if len(parts) == 2:
                person = parts[0].strip()
                spouse = parts[1].strip().rstrip(".")
                extra_facts.append(f"{person} is married to {spouse}.")
                extra_facts.append(f"{person} is the one married to {spouse}.")
                extra_facts.append(f"The person married to {spouse} is {person}.")
                continue

        if "is abroad" in line_lower:
            person = line.split("is abroad")[0].strip()
            extra_facts.append(f"{person} is abroad.")
            extra_facts.append(f"{person} currently lives abroad.")
            extra_facts.append(f"The person who is abroad is {person}.")
            continue

        extra_facts.append(line)

    derived: list[str] = []
    all_grandchildren: list[str] = []

    for parent, children in parent_to_children.items():
        names = [c for c, _ in children]
        for child, gender in children:
            if parent == "User":
                derived.append(f"The User has a {gender} named {child}.")
                derived.append(f"{child} is the User's {gender}.")
            else:
                derived.append(f"{child} ({gender}) is a child of {parent}.")
                derived.append(f"{parent} is {child}'s parent.")
                parent_gender = gender_map.get(parent, "unknown")
                if parent_gender == "daughter":
                    derived.append(f"{child}'s mother is {parent}.")
                elif parent_gender == "son":
                    derived.append(f"{child}'s father is {parent}.")
                else:
                    derived.append(f"{child}'s parent is {parent}.")
                grandparent = child_to_parent.get(parent)
                if grandparent:
                    gp = "the User" if grandparent == "User" else grandparent
                    derived.append(
                        f"{child} is {gp}'s grandchild (through {parent})."
                    )
                    if grandparent == "User":
                        all_grandchildren.append(child)

        if len(names) > 1:
            for name in names:
                siblings = [s for s in names if s != name]
                derived.append(f"{name}'s siblings are: {', '.join(siblings)}.")

    user_children = parent_to_children.get("User", [])
    if user_children:
        names_str = ", ".join([f"{n} ({g})" for n, g in user_children])
        derived.append(f"The User's children are: {names_str}.")

    if all_grandchildren:
        derived.append(
            f"The User's grandchildren are: {', '.join(all_grandchildren)}."
        )

    derived.extend(extra_facts)
    return "\n".join(derived)



_COMMON_CAPITALIZED_SKIP = {
    "I", "Today", "Yesterday", "Tomorrow", "Please", "Thanks", "Thank",
    "Hello", "Hi", "Yes", "No", "Okay", "Ok", "Morning", "Evening", "Afternoon",
}


#  EchoBrain 
class EchoBrain:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3.6-flash",
            temperature=0.1,
            google_api_key=GOOGLE_API_KEY
        )
        self._derived_facts: str = ""
        self._chat_history: list = []
        self.patient_name: str = ""
        self._known_names: set[str] = set()
        self._evaluated_candidates: set[str] = set()
        self.sentinel = Sentinel()
        self.sentiment = SentimentTracker(log_path="data/sentiment_log.json")
        self.reminders = ReminderManager(reminder_file="data/reminders.json")

    def initialize_memory(self, text_data: str) -> str:
        self._derived_facts = derive_relationships(text_data)
        self._chat_history = []
        self.sentinel.reset()
        self.sentiment.reset()
        db.init_db()

        name_match = re.search(r"the user is (\w+)", text_data, re.I)
        self.patient_name = name_match.group(1) if name_match else ""

        raw_names = set(re.findall(r"\b[A-Z][a-z]+\b", text_data))
        self._known_names = {n.lower() for n in raw_names} | {self.patient_name.lower()}
        # Names already learned in previous sessions shouldn't be re-flagged every time
        self._known_names |= db.known_fact_names()
        self._evaluated_candidates = set()

        return "Memory Bank is Ready!"

    def _detect_new_info(self, question: str) -> list[str]:
        """Simple heuristic: capitalized words in the question that aren't
        already in family_memories.txt are treated as possibly-new names."""
        words = question.split()
        candidates = []
        for i, w in enumerate(words):
            cleaned = w.strip(".,!?;:\"'")
            if i == 0 or not cleaned:
                continue  # skip sentence-initial word to avoid false positives
            if re.match(r"^[A-Z][a-z]+$", cleaned) and cleaned not in _COMMON_CAPITALIZED_SKIP:
                if cleaned.lower() not in self._known_names:
                    candidates.append(cleaned)
        return candidates

    def _llm_confirm_new_info(self, question: str, candidates: list[str]) -> list[dict]:
        """Second, smarter pass — only called on candidates the cheap heuristic
        already flagged. Asks the LLM to rule out typos/mishearings of known
        names and common words, and to write a clean one-line summary for
        anything genuinely new. Fails safe: any error just skips this turn."""
        if not candidates:
            return []
        prompt = f"""You are reviewing one message from an Alzheimer's patient's conversation
with a memory-companion AI, checking for genuinely new personal information.

EXISTING FAMILY FACTS:
{self._derived_facts}

THE PATIENT JUST SAID:
"{question}"

A simple word-matching heuristic flagged these words as possibly-new: {", ".join(candidates)}

For each flagged word, decide:
- Is it a genuinely NEW piece of personal information (a new person, relationship,
  preference, or event) that is NOT already covered by the existing family facts,
  and NOT a typo or mishearing of a name that already exists there?
- If yes: write ONE short, clear sentence summarizing what was said.
- If no (it's a known name spelled differently, a common word, or not real new
  information): leave it out entirely.

Respond with ONLY valid JSON, no markdown formatting, no extra text, in exactly
this shape:
{{"new_facts": [{{"name": "Priya", "summary": "Mentioned a friend named Priya who visited recently."}}]}}

If none are genuinely new, respond with exactly: {{"new_facts": []}}
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            raw = response.content
            if isinstance(raw, list):
                raw = "".join(
                    b.get("text", "") if isinstance(b, dict) else str(b) for b in raw
                )
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(json)?", "", cleaned).rstrip("`").strip()
            data = json.loads(cleaned)
            facts = data.get("new_facts", [])
            return [f for f in facts if f.get("name") and f.get("summary")]
        except Exception as exc:
            logger.exception("New-info LLM confirmation failed: %s", exc)
            return []

    def _find_requested_photo(self, question: str) -> str | None:
        """Only returns a photo when the message clearly asks to see one
        (e.g. 'show me Sivapriya', 'what does Anil look like') — not on
        every passing mention of a person who happens to have a saved photo."""
        if not _PHOTO_TRIGGER_RE.search(question):
            return None
        if not PHOTOS_DIR.exists():
            return None
        q_lower = question.lower()
        for f in PHOTOS_DIR.iterdir():
            if f.is_file() and f.stem.lower() and f.stem.lower() in q_lower:
                return f.name
        return None

    def ask(self, question: str) -> dict:
        """
        Returns:
            answer, mood, mood_emoji, is_repeat,
            repeat_count, alert_caregiver, due_reminder
        """
        if not question or not question.strip():
            return {
                "answer": "I didn't catch that. Could you ask me again?",
                "mood": "calm", "mood_emoji": "😌",
                "is_repeat": False, "repeat_count": 1,
                "alert_caregiver": False, "due_reminder": None,
                "new_info_detected": False, "new_info_names": [], "new_info_summaries": [], "photo_url": None,
            }
        if not self._derived_facts:
            return {
                "answer": "I don't have any memories yet.",
                "mood": "calm", "mood_emoji": "😌",
                "is_repeat": False, "repeat_count": 1,
                "alert_caregiver": False, "due_reminder": None,
                "new_info_detected": False, "new_info_names": [], "new_info_summaries": [], "photo_url": None,
            }

        #  Sentiment 
        sentiment_result = self.sentiment.analyze(question)
        mood = sentiment_result["mood"]
        is_distressed = sentiment_result["is_distressed"]
        is_lonely = mood == "lonely"

        #  Repeated question 
        sentinel_result = self.sentinel.check(question)
        prefix = sentinel_result["prefix"]
        is_repeat = sentinel_result["is_repeat"]

        #  Reminders 
        reminder_context = self.reminders.format_for_llm()
        due_alert = self.reminders.format_due_alert()

        #  New-info detection: cheap heuristic first, LLM confirms only flagged words 
        candidate_names = self._detect_new_info(question)
        unseen_candidates = [c for c in candidate_names if c.lower() not in self._evaluated_candidates]

        confirmed_facts: list[dict] = []
        if unseen_candidates:
            confirmed_facts = self._llm_confirm_new_info(question, unseen_candidates)
            for c in unseen_candidates:
                self._evaluated_candidates.add(c.lower())  # don't re-spend a call on the same word again

        for fact in confirmed_facts:
            name = fact["name"].strip()
            summary = fact["summary"].strip()
            db.add_learned_fact(name, summary)
            self._known_names.add(name.lower())

        learned_facts_text = db.get_context_facts_text() or "None yet."

        #  Build LLM question 
        comfort_hint = ""
        if is_distressed or is_lonely:
            comfort_hint = "[Patient seems emotional. Lead with comfort first.] "

        llm_question = f"{comfort_hint}{prefix}{question}"

        #  Call LLM 
        system_msg = SystemMessage(content=SYSTEM_PROMPT.format(
            context=self._derived_facts,
            learned_facts=learned_facts_text,
            reminders=reminder_context,
        ))
        messages = [system_msg] + self._chat_history + [
            HumanMessage(content=llm_question)
        ]
        try:
            response = self.llm.invoke(messages)
            raw = response.content
            if isinstance(raw, str):
                answer = raw
            elif isinstance(raw, list):
                answer = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in raw
                    if not isinstance(block, dict) or block.get("type") == "text"
                )
            else:
                answer = str(raw)
        except Exception as exc:
            logger.exception("LLM call failed: %s", exc)
            answer = "I'm having a little trouble thinking right now. Could we try that again in a moment?"

        final_answer = f"{prefix}{answer}" if prefix else answer

        #  History (in-memory, for prompt context) 
        self._chat_history.append(HumanMessage(content=question))
        self._chat_history.append(AIMessage(content=final_answer))
        if len(self._chat_history) > 20:
            self._chat_history = self._chat_history[-20:]

        #  History (persisted, permanent) 
        db.log_message("user", question, mood)
        db.log_message("assistant", final_answer, mood)

        #  Photo lookup (explicit trigger only) 
        photo_file = self._find_requested_photo(question)

        return {
            "answer": final_answer,
            "mood": mood,
            "mood_emoji": MOOD_EMOJI[mood],
            "is_repeat": is_repeat,
            "repeat_count": sentinel_result["count"],
            "alert_caregiver": sentiment_result["alert_caregiver"],
            "due_reminder": due_alert,
            "new_info_detected": len(confirmed_facts) > 0,
            "new_info_names": [f["name"] for f in confirmed_facts],
            "new_info_summaries": [f["summary"] for f in confirmed_facts],
            "photo_url": f"/photos/{photo_file}" if photo_file else None,
        }

    def get_repeated_questions(self) -> list[dict]:
        return self.sentinel.get_repeated_questions()

    def get_mood_summary(self) -> dict:
        return self.sentiment.get_session_summary()

    def save_session(self):
        self.sentiment.save_session()

    def reset_conversation(self):
        self._chat_history = []
        self.sentinel.reset()
        self.sentiment.reset()


#  Quick test 
if __name__ == "__main__":
    brain = EchoBrain()
    with open("data/family_memories.txt", "r", encoding="utf-8") as f:
        memories = f.read()

    print("Creating memory bank...")
    print(brain.initialize_memory(memories))

    # Add a test reminder
    brain.reminders.add_reminder(
        "Blood pressure tablet", "medication", "09:00", notes="Take with water"
    )
    brain.reminders.add_reminder("Drink water", "task", "10:00")

    tests = [
        "Who is Haripriya's mother?",
        "What do I need to do today?",
        "Did I take my medicine?",
        "Who are my grandchildren?",
    ]

    for q in tests:
        result = brain.ask(q)
        print(f"\nQ: {q}")
        print(f"A: {result['answer']}")
        if result["due_reminder"]:
            print(f"⏰ DUE: {result['due_reminder']}")
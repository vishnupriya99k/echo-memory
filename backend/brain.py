import re
import os
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
from sentinel import Sentinel
from sentiment import SentimentTracker, MOOD_EMOJI
from reminders import ReminderManager

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

# ── System prompt ─────────────────────────────────────────────────────────────
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

{reminders}
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
        self.sentinel = Sentinel()
        self.sentiment = SentimentTracker(log_path="data/sentiment_log.json")
        self.reminders = ReminderManager(reminder_file="data/reminders.json")

    def initialize_memory(self, text_data: str) -> str:
        self._derived_facts = derive_relationships(text_data)
        self._chat_history = []
        self.sentinel.reset()
        self.sentiment.reset()
        return "Memory Bank is Ready!"

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
            }
        if not self._derived_facts:
            return {
                "answer": "I don't have any memories yet.",
                "mood": "calm", "mood_emoji": "😌",
                "is_repeat": False, "repeat_count": 1,
                "alert_caregiver": False, "due_reminder": None,
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

        #  Build LLM question 
        comfort_hint = ""
        if is_distressed or is_lonely:
            comfort_hint = "[Patient seems emotional. Lead with comfort first.] "

        llm_question = f"{comfort_hint}{prefix}{question}"

        #  Call LLM 
        system_msg = SystemMessage(content=SYSTEM_PROMPT.format(
            context=self._derived_facts,
            reminders=reminder_context,
        ))
        messages = [system_msg] + self._chat_history + [
            HumanMessage(content=llm_question)
        ]
        response = self.llm.invoke(messages)
        answer = response.content
        final_answer = f"{prefix}{answer}" if prefix else answer

        #  History 
        self._chat_history.append(HumanMessage(content=question))
        self._chat_history.append(AIMessage(content=final_answer))
        if len(self._chat_history) > 20:
            self._chat_history = self._chat_history[-20:]

        return {
            "answer": final_answer,
            "mood": mood,
            "mood_emoji": MOOD_EMOJI[mood],
            "is_repeat": is_repeat,
            "repeat_count": sentinel_result["count"],
            "alert_caregiver": sentiment_result["alert_caregiver"],
            "due_reminder": due_alert,
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
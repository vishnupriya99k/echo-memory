"""
reminders.py — Medication & Task Reminder System
Borrowed concept from memorAi (praatibhsurana/memorAi).

Family members add reminders (medications, tasks, appointments).
The system checks which reminders are due and surfaces them
proactively in the chat. Patients can also ask "what do I need
to do today?" to get a summary.

Reminder types:
  - medication  : pills, tablets, syrup
  - task        : drink water, exercise, eat lunch
  - appointment : doctor visits, family calls
"""

import json
from datetime import datetime, date, time
from pathlib import Path


#  Constants 
REMINDER_FILE = "data/reminders.json"

TYPE_EMOJI = {
    "medication":  "💊",
    "task":        "✅",
    "appointment": "📅",
}

# How many minutes before/after scheduled time to show reminder
REMINDER_WINDOW_MINUTES = 30


#  Data helpers 
def _load(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(path: str, data: list[dict]):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


#  ReminderManager 
class ReminderManager:
    """
    Manages medication and task reminders.
    Attach one instance to EchoBrain.
    """

    def __init__(self, reminder_file: str = REMINDER_FILE):
        self.reminder_file = reminder_file

    #  CRUD 
    def add_reminder(
        self,
        label: str,
        reminder_type: str,        # medication | task | appointment
        time_str: str,             # "HH:MM" 24h format
        days: list[str] | None = None,   # ["monday","tuesday",...] or None=daily
        notes: str = "",
    ) -> dict:
        """Add a new reminder. Returns the created reminder dict."""
        reminders = _load(self.reminder_file)
        reminder = {
            "id": len(reminders) + 1,
            "label": label,
            "type": reminder_type,
            "time": time_str,        # "09:00"
            "days": days or "daily", # "daily" or list of day names
            "notes": notes,
            "created": datetime.now().isoformat(),
            "completed_dates": [],   # dates where patient confirmed done
        }
        reminders.append(reminder)
        _save(self.reminder_file, reminders)
        return reminder

    def get_all(self) -> list[dict]:
        return _load(self.reminder_file)

    def delete_reminder(self, reminder_id: int) -> bool:
        reminders = _load(self.reminder_file)
        new = [r for r in reminders if r["id"] != reminder_id]
        if len(new) < len(reminders):
            _save(self.reminder_file, new)
            return True
        return False

    def mark_done(self, reminder_id: int) -> bool:
        """Mark a reminder as completed for today."""
        reminders = _load(self.reminder_file)
        today = date.today().isoformat()
        for r in reminders:
            if r["id"] == reminder_id:
                if today not in r["completed_dates"]:
                    r["completed_dates"].append(today)
                _save(self.reminder_file, reminders)
                return True
        return False

    #  Due check 
    def get_due_now(self) -> list[dict]:
        """
        Return reminders that are due within the time window right now.
        Excludes already-completed ones for today.
        """
        reminders = _load(self.reminder_file)
        now = datetime.now()
        today_str = date.today().isoformat()
        today_day = now.strftime("%A").lower()   # e.g. "monday"
        due = []

        for r in reminders:
            # Check day match
            days = r.get("days", "daily")
            if days != "daily" and today_day not in days:
                continue

            # Check already done today
            if today_str in r.get("completed_dates", []):
                continue

            # Check time window
            try:
                h, m = map(int, r["time"].split(":"))
                scheduled = now.replace(hour=h, minute=m, second=0, microsecond=0)
                diff_minutes = (now - scheduled).total_seconds() / 60
                # Due if within window (before or after)
                if -5 <= diff_minutes <= REMINDER_WINDOW_MINUTES:
                    due.append(r)
            except Exception:
                continue

        return due

    def get_todays_reminders(self) -> list[dict]:
        """All reminders scheduled for today, with completion status."""
        reminders = _load(self.reminder_file)
        today_str = date.today().isoformat()
        today_day = datetime.now().strftime("%A").lower()
        result = []

        for r in reminders:
            days = r.get("days", "daily")
            if days != "daily" and today_day not in days:
                continue
            r["done_today"] = today_str in r.get("completed_dates", [])
            result.append(r)

        # Sort by time
        result.sort(key=lambda x: x.get("time", "00:00"))
        return result

    def format_for_llm(self) -> str:
        """Format today's reminders as facts for the LLM context."""
        todays = self.get_todays_reminders()
        if not todays:
            return "No reminders scheduled for today."

        lines = ["TODAY'S REMINDERS:"]
        for r in todays:
            emoji = TYPE_EMOJI.get(r["type"], "🔔")
            done = "✅ Done" if r["done_today"] else "⏰ Pending"
            note = f" ({r['notes']})" if r.get("notes") else ""
            lines.append(
                f"{emoji} {r['time']} — {r['label']}{note} [{done}]"
            )
        return "\n".join(lines)

    def format_due_alert(self) -> str | None:
        """Return a friendly alert string if any reminders are due now."""
        due = self.get_due_now()
        if not due:
            return None

        parts = []
        for r in due:
            emoji = TYPE_EMOJI.get(r["type"], "🔔")
            note = f" — {r['notes']}" if r.get("notes") else ""
            parts.append(f"{emoji} {r['label']} at {r['time']}{note}")

        if len(parts) == 1:
            return f"Reminder: {parts[0]}"
        return "Reminders due:\n" + "\n".join(f"• {p}" for p in parts)


#  Quick test 
if __name__ == "__main__":
    import os
    os.makedirs("data", exist_ok=True)

    mgr = ReminderManager("data/reminders_test.json")

    # Add some reminders
    mgr.add_reminder("Blood pressure tablet", "medication", "09:00",
                     notes="Take with water")
    mgr.add_reminder("Drink a glass of water", "task", "10:00")
    mgr.add_reminder("Lunch", "task", "13:00")
    mgr.add_reminder("Evening walk", "task", "17:00",
                     days=["monday", "wednesday", "friday"])
    mgr.add_reminder("Video call with Vijaya", "appointment", "18:00",
                     days=["sunday"])

    print("--- All Reminders ---")
    for r in mgr.get_all():
        emoji = TYPE_EMOJI.get(r["type"], "🔔")
        days = r["days"] if isinstance(r["days"], str) else ", ".join(r["days"])
        print(f"  {emoji} [{r['id']}] {r['label']} at {r['time']} ({days})")

    print("\n--- Today's Reminders ---")
    for r in mgr.get_todays_reminders():
        emoji = TYPE_EMOJI.get(r["type"], "🔔")
        print(f"  {emoji} {r['time']} {r['label']}")

    print("\n--- LLM Format ---")
    print(mgr.format_for_llm())

    print("\n--- Due Now ---")
    due_alert = mgr.format_due_alert()
    print(due_alert or "Nothing due right now.")

    # Cleanup test file
    import os
    if os.path.exists("data/reminders_test.json"):
        os.remove("data/reminders_test.json")
    print("\n Test complete.")
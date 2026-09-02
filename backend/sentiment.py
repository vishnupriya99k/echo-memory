"""
sentiment.py — Patient Mood Tracker
Borrowed concept from memorAi (praatibhsurana/memorAi).

Analyzes every patient message for emotional state and logs it
with a timestamp. Caregivers can review the mood log to understand
how the patient felt throughout the day and spot distress patterns.

Mood categories (clinically relevant for Alzheimer's care):
  - happy      : positive, cheerful, grateful
  - calm       : neutral, relaxed, comfortable
  - confused   : uncertain, lost, forgetful
  - distressed : anxious, scared, upset, angry
  - lonely     : missing someone, feeling alone
"""

import json
import os
from datetime import datetime
from pathlib import Path


#  Keyword maps for rule-based detection (fast, no API needed) 
MOOD_KEYWORDS = {
    "happy": [
        "happy", "glad", "thank", "thanks", "wonderful", "great", "love",
        "beautiful", "nice", "good", "joy", "lovely", "blessed", "smile",
        "laugh", "excited", "pleased", "delighted", "proud"
    ],
    "distressed": [
        "scared", "afraid", "worry", "worried", "anxious", "panic", "help",
        "lost", "alone", "forget", "forgotten", "why", "where am i",
        "don't know", "scared", "cry", "crying", "hurt", "pain", "angry",
        "upset", "terrible", "horrible", "frightened", "nightmare"
    ],
    "confused": [
        "who", "what", "when", "where", "which", "remember", "remind",
        "forget", "forgot", "confused", "not sure", "i think", "maybe",
        "don't remember", "can't recall", "which one", "again", "repeat",
        "tell me again", "already", "said that"
    ],
    "lonely": [
        "miss", "missing", "alone", "lonely", "nobody", "no one", "family",
        "where is", "when will", "come back", "visit", "see them", "wish"
    ],
    "calm": []   # default fallback
}

# Priority order — distressed should override confused etc.
MOOD_PRIORITY = ["distressed", "lonely", "confused", "happy", "calm"]

# Emoji for UI display
MOOD_EMOJI = {
    "happy":     "😊",
    "calm":      "😌",
    "confused":  "😕",
    "distressed":"😟",
    "lonely":    "🥺",
}

# Caregiver alert threshold — alert if distressed N times in a session
DISTRESS_ALERT_THRESHOLD = 3


def detect_mood(text: str) -> str:
    """
    Rule-based mood detection from patient message text.
    Returns one of: happy, calm, confused, distressed, lonely
    """
    text_lower = text.lower()
    scores = {mood: 0 for mood in MOOD_KEYWORDS}

    for mood, keywords in MOOD_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[mood] += 1

    # Pick highest scoring mood in priority order
    for mood in MOOD_PRIORITY:
        if scores[mood] > 0:
            return mood

    return "calm"   # default


class SentimentTracker:
    """
    Tracks patient mood across a session and persists logs to disk.
    Attach one instance to EchoBrain.
    """

    def __init__(self, log_path: str = "data/sentiment_log.json"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_log: list[dict] = []   # current session entries
        self._distress_count: int = 0

    def analyze(self, text: str) -> dict:
        """
        Analyze a patient message, log the mood, and return result.

        Returns:
            {
                "mood": str,
                "emoji": str,
                "is_distressed": bool,
                "alert_caregiver": bool,   # True if distress threshold reached
                "timestamp": str,
            }
        """
        mood = detect_mood(text)
        emoji = MOOD_EMOJI[mood]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_distressed = mood == "distressed"

        if is_distressed:
            self._distress_count += 1

        entry = {
            "timestamp": timestamp,
            "mood": mood,
            "emoji": emoji,
            "message_snippet": text[:80] + ("..." if len(text) > 80 else ""),
        }
        self._session_log.append(entry)

        return {
            "mood": mood,
            "emoji": emoji,
            "is_distressed": is_distressed,
            "alert_caregiver": self._distress_count >= DISTRESS_ALERT_THRESHOLD,
            "timestamp": timestamp,
        }

    def get_session_summary(self) -> dict:
        """
        Return a summary of the current session's mood distribution.
        Useful for caregiver dashboard.
        """
        if not self._session_log:
            return {"total": 0, "moods": {}, "dominant_mood": "calm"}

        mood_counts: dict[str, int] = {}
        for entry in self._session_log:
            mood = entry["mood"]
            mood_counts[mood] = mood_counts.get(mood, 0) + 1

        dominant = max(mood_counts, key=mood_counts.get)
        return {
            "total": len(self._session_log),
            "moods": mood_counts,
            "dominant_mood": dominant,
            "distress_count": self._distress_count,
        }

    def save_session(self):
        """Append current session to the persistent JSON log file."""
        if not self._session_log:
            return

        existing = []
        if self.log_path.exists():
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        session_entry = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "session_time": datetime.now().strftime("%H:%M:%S"),
            "summary": self.get_session_summary(),
            "entries": self._session_log,
        }
        existing.append(session_entry)

        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

    def load_history(self) -> list[dict]:
        """Load all past sessions from the log file."""
        if not self.log_path.exists():
            return []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def reset(self):
        """Clear current session (does NOT delete saved log)."""
        self._session_log = []
        self._distress_count = 0


#  Quick test 
if __name__ == "__main__":
    tracker = SentimentTracker(log_path="data/sentiment_log.json")

    test_messages = [
        "Who is Haripriya's mother?",           # confused
        "I miss my daughter so much",            # lonely
        "Thank you, that makes me happy!",       # happy
        "I don't know where I am, I'm scared",  # distressed
        "Tell me again who Vijaya is",           # confused
        "Where is everyone? I feel so alone",   # lonely + distressed
        "That's wonderful, I'm so proud",        # happy
    ]

    print("--- Mood Analysis ---")
    for msg in test_messages:
        result = tracker.analyze(msg)
        alert = "  ALERT CAREGIVER" if result["alert_caregiver"] else ""
        print(f"{result['emoji']} [{result['mood']:10}] {msg[:50]}{alert}")

    print("\n--- Session Summary ---")
    summary = tracker.get_session_summary()
    print(f"Total messages : {summary['total']}")
    print(f"Dominant mood  : {summary['dominant_mood']}")
    print(f"Distress count : {summary['distress_count']}")
    print(f"Mood breakdown : {summary['moods']}")

    tracker.save_session()
    print("\n Session saved to data/sentiment_log.json")
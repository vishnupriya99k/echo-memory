"""
sentinel.py — Repeated Question Detector
Borrowed concept from DementiaBot (memiiso/dementiabot).

Alzheimer's patients frequently ask the same question multiple times
because short-term memory encoding is impaired. This module:
  1. Detects when a new question is semantically similar to a recent one
  2. Tracks how many times it has been asked
  3. Returns a flag + a warm reassurance prefix so the LLM never sounds
     robotic or impatient on repeated questions
"""

import re
from difflib import SequenceMatcher


# Config 
SIMILARITY_THRESHOLD = 0.75   # 0-1, how similar two questions must be to count
MAX_HISTORY = 20              # how many past questions to remember


#  Reassurance prefixes (rotated so it never sounds scripted) 
REASSURANCE_PREFIXES = [
    "Of course, happy to remind you! ",
    "That's completely fine to ask again. ",
    "I'm always here to help you remember. ",
    "No worries at all — let me tell you again. ",
    "It's perfectly okay to ask. ",
    "I love that you're curious! ",
]


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation for fair comparison."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _similarity(a: str, b: str) -> float:
    """Return 0-1 similarity score between two strings."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


class Sentinel:
    """
    Tracks question history and detects repeated questions.
    Attach one instance to EchoBrain.
    """

    def __init__(self):
        self._history: list[dict] = []
        # history entry: {"question": str, "count": int, "prefix_index": int}
        self._prefix_counter = 0

    def check(self, question: str) -> dict:
        """
        Check if this question is a repeat.

        Returns:
            {
                "is_repeat": bool,
                "count": int,           # how many times asked (1 = first time)
                "prefix": str,          # warm reassurance prefix to prepend
                "matched": str | None,  # the original phrasing it matched
            }
        """
        # Look for a similar question in history
        for entry in self._history:
            score = _similarity(question, entry["question"])
            if score >= SIMILARITY_THRESHOLD:
                entry["count"] += 1
                prefix = REASSURANCE_PREFIXES[
                    self._prefix_counter % len(REASSURANCE_PREFIXES)
                ]
                self._prefix_counter += 1
                return {
                    "is_repeat": True,
                    "count": entry["count"],
                    "prefix": prefix,
                    "matched": entry["question"],
                }

        # New question — add to history
        if len(self._history) >= MAX_HISTORY:
            self._history.pop(0)   # drop oldest
        self._history.append({"question": question, "count": 1})
        return {
            "is_repeat": False,
            "count": 1,
            "prefix": "",
            "matched": None,
        }

    def reset(self):
        """Clear history (call when a new session starts)."""
        self._history = []
        self._prefix_counter = 0

    def get_repeated_questions(self) -> list[dict]:
        """Return all questions asked more than once — for caregiver dashboard."""
        return [e for e in self._history if e["count"] > 1]


#  Quick test 
if __name__ == "__main__":
    s = Sentinel()

    questions = [
        "Who is Haripriya's mother?",
        "Who are my grandchildren?",
        "Who is haripriya's mom?",      # repeat (different phrasing)
        "Tell me about Vijaya",
        "Who is Haripriya's mother?",   # exact repeat
        "Who are my grandkids?",        # repeat of grandchildren
        "What is my name?",
    ]

    for q in questions:
        result = s.check(q)
        status = f"REPEAT #{result['count']}" if result["is_repeat"] else "NEW"
        print(f"[{status}] {q}")
        if result["is_repeat"]:
            print(f"         → Prefix: '{result['prefix']}'")
            print(f"         → Matched: '{result['matched']}'")

    print("\n--- Repeated Questions (for caregiver) ---")
    for r in s.get_repeated_questions():
        print(f"  '{r['question']}' asked {r['count']} times")
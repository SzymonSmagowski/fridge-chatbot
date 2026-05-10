"""Cheap on-device locale detection for chat/voice graph turn entry.

We deliberately avoid an LLM call here — adding a round-trip per turn just to
classify language adds 100-300 ms to every interaction, and the kitchen-floor
voice latency budget is <1.5s end-to-end. Polish has very distinctive
diacritics (`ąćęłńóśźż`); their presence is sufficient evidence to flip the
locale. For Polish messages without diacritics ("dodaj mleko"), a small word
list catches the most common imperatives. Anything else falls back to English.

False-negative cost: the user types/says a Polish phrase with no diacritic and
no word in the heuristic list → assistant replies in English for that turn.
This is recoverable: the user can repeat with a more distinctly Polish
phrasing, or pin `voice_locale="pl"` in family preferences (future amendment).

False-positive cost: an English message containing a Polish diacritic or
matching word ("not" matches no entry; "Łódź" matches; "tak" — Polish "yes" —
matches if the user typed it as a literal English word, unlikely). Acceptable.
"""
from __future__ import annotations

from src.llm_graphs.shared.prompts import Locale

_POLISH_DIACRITICS = frozenset("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")

# Most common Polish imperatives + question words + greetings the fridge will
# hear in everyday use. Lowercase comparison only.
_POLISH_HINTS: frozenset[str] = frozenset(
    {
        "dodaj",
        "usuń",
        "usun",
        "pokaż",
        "pokaz",
        "co",
        "kto",
        "kiedy",
        "jak",
        "ile",
        "czy",
        "tak",
        "nie",
        "chcę",
        "chce",
        "proszę",
        "prosze",
        "lodówko",
        "lodowko",
        "lodówka",
        "lodowka",
        "hej",
        "cześć",
        "czesc",
        "dzień",
        "dzien",
        "dobry",
        "wieczór",
        "wieczor",
        "mleko",
        "chleb",
    }
)


def detect_locale(text: str) -> Locale:
    """Return `"pl"` when the text looks Polish, else `"en"`."""
    if not text:
        return "en"
    if any(c in _POLISH_DIACRITICS for c in text):
        return "pl"
    words = set(text.lower().split())
    if words & _POLISH_HINTS:
        return "pl"
    return "en"

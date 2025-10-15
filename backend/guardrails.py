import re
from typing import List

RED_FLAG_KEYWORDS = [
    'chest pain', 'shortness of breath', 'difficulty breathing', 'severe bleeding',
    'loss of consciousness', 'sudden weakness', 'slurred speech', 'facial droop',
    'very high fever', 'seizure', 'unresponsive', 'severe allergic reaction',
    'anaphylaxis', 'severe abdominal pain', 'vomiting blood'
]

SELF_HARM_KEYWORDS = [
    'suicide', 'kill myself', 'end my life', 'self harm', 'hurt myself', 'cut myself','end everything','end it once for all'
]

PII_PATTERNS = {
    'phone': re.compile(r'\b\d{10}\b'),
    'email': re.compile(r'\b[\w\.-]+@[\w\.-]+\.[A-Za-z]{2,}\b'),
    'address': re.compile(r'\d{1,5}\s\w+\s\w+'),  # simple address heuristic
    'name': re.compile(r'\b(Name is|I am|My name is)\s+[A-Z][a-z]+')
}

def sanitize_input(text: str):
    """Remove personally identifiable info (PII) such as phone numbers or emails."""
    removed = []
    sanitized = text
    for key, pattern in PII_PATTERNS.items():
        if pattern.search(sanitized):
            sanitized = pattern.sub(f'<{key.upper()}_REDACTED>', sanitized)
            removed.append(key)
    return sanitized.strip(), removed

def detect_red_flags(text: str) -> List[str]:
    """Return list of red flag keywords found in input."""
    found = []
    lowered = text.lower()
    for keyword in RED_FLAG_KEYWORDS:
        if keyword in lowered:
            found.append(keyword)
    return found

def check_for_self_harm(text: str) -> bool:
    """Check if user mentions self-harm or suicidal ideation."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in SELF_HARM_KEYWORDS)

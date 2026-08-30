KNOWN_SKILLS = [
    "admin",
    "bookkeeping",
    "cashier",
    "communication",
    "customer service",
    "data entry",
    "excel",
    "forklift",
    "google workspace",
    "marketing",
    "microsoft office",
    "python",
    "retail",
    "sales",
    "social media",
    "typing",
    "warehouse",
    "word",
]


def extract_required_skills(text: str) -> list[str]:
    lowered = text.lower()
    return [skill for skill in KNOWN_SKILLS if skill in lowered]


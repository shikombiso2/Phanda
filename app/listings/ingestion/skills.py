"""Keyword-based skill tagging: source text -> a list of canonical skill names.

Replaces a flat list of 18 substring checks. Two problems with substring
matching specifically: it fires on partial words ("administration" contains
"admin", "keyword" contains "word"), and it has no way to recognise the same
skill written differently ("MS Excel", "Microsoft Excel", "Excel" are all one
skill). This module fixes both: every phrase is matched on a word boundary,
and each canonical skill can list any number of alias phrases that all
resolve to it.

This is still a keyword lookup, not NLP -- deliberately. Growing coverage is
adding an entry to SKILL_VOCABULARY, not writing code. See
docs/RECOMMENDATIONS.md for why a heavier approach (embeddings, an NLP
skill-extraction model) is a post-launch upgrade, not a launch blocker.
"""

from __future__ import annotations

import re

# canonical skill -> every surface form that should resolve to it (the
# canonical name is matched automatically; list additional aliases only).
SKILL_VOCABULARY: dict[str, list[str]] = {
    # Office / admin
    "admin": ["administration", "administrative", "office administration"],
    "data entry": ["capturing", "data capturing"],
    "filing": ["record keeping", "records management"],
    "typing": ["keyboarding"],
    "reception": ["receptionist", "front desk"],
    "scheduling": ["diary management", "calendar management"],
    "bookkeeping": ["book keeping"],
    "invoicing": ["billing"],
    "stock control": ["inventory control", "inventory management", "stock management"],
    "procurement": ["purchasing"],
    "excel": ["ms excel", "microsoft excel", "spreadsheets"],
    "word": ["ms word", "microsoft word"],
    "powerpoint": ["ms powerpoint", "microsoft powerpoint"],
    "microsoft office": ["ms office", "office suite"],
    "google workspace": ["google docs", "google sheets", "g suite"],
    "email": ["email correspondence", "outlook"],
    "sage": ["sage accounting", "sage pastel", "pastel"],
    "payroll": ["payroll administration"],
    # Customer-facing / retail
    "customer service": ["client service", "customer care", "client relations"],
    "cashier": ["till operations", "point of sale", "pos"],
    "retail": ["retail sales", "shop assistant"],
    "sales": ["selling", "sales representative"],
    "merchandising": ["visual merchandising", "shelf packing", "packing shelves"],
    "upselling": ["cross-selling"],
    "telesales": ["telemarketing", "cold calling"],
    "call centre": ["call center", "contact centre", "contact center"],
    "complaints handling": ["query resolution", "customer complaints"],
    "hospitality": ["front of house"],
    "waitering": ["waitressing", "waiter", "waitress"],
    "bartending": ["barista"],
    "housekeeping": ["cleaning"],
    "food preparation": ["food prep", "cooking"],
    # Warehouse / logistics / trades
    "warehouse": ["warehousing"],
    "forklift": ["forklift operation", "forklift license", "forklift licence"],
    "picking and packing": ["order picking", "pick and pack"],
    "driving": ["driver's license", "drivers license", "code 8", "code 10", "code 14"],
    "delivery": ["courier"],
    "loading": ["offloading"],
    "quality control": ["qc", "quality assurance", "qa"],
    "machine operation": ["machine operator"],
    "welding": [],
    "electrical": ["electrician"],
    "plumbing": ["plumber"],
    "carpentry": ["carpenter"],
    "artisan": ["apprenticeship trade"],
    "health and safety": ["ohs", "occupational health and safety"],
    # Communication / soft skills
    "communication": ["communication skills", "verbal communication", "written communication"],
    "teamwork": ["team player", "team work"],
    "time management": [],
    "problem solving": ["problem-solving"],
    "attention to detail": [],
    "leadership": ["team leadership", "supervisory"],
    "training": ["mentoring", "coaching"],
    "conflict resolution": [],
    "negotiation": [],
    "multitasking": ["multi-tasking"],
    "planning": ["organisational skills", "organizational skills"],
    "adaptability": ["flexibility"],
    # Marketing / digital
    "marketing": ["digital marketing"],
    "social media": ["social media management", "facebook", "instagram", "tiktok marketing"],
    "content creation": ["copywriting", "content writing"],
    "graphic design": ["canva", "photoshop"],
    "seo": ["search engine optimisation", "search engine optimization"],
    "email marketing": ["mailchimp"],
    "photography": ["videography"],
    "video editing": ["editing"],
    # Finance / admin-adjacent
    "accounting": ["bookkeeper", "financial administration"],
    "budgeting": ["financial planning"],
    "reconciliations": ["bank reconciliation"],
    "debtors": ["creditors", "accounts payable", "accounts receivable"],
    "tax": ["taxation", "sars"],
    # Tech (kept for listings that do need it -- entry-level IT/support roles exist too)
    "python": [],
    "excel vba": ["vba", "macros"],
    "sql": ["databases"],
    "computer literacy": ["basic computer skills", "computer skills"],
    "troubleshooting": ["it support", "technical support", "help desk"],
    "networking": ["network administration"],
    "data analysis": ["data analytics"],
    # Education / childcare / care work
    "childcare": ["babysitting", "au pair"],
    "teaching": ["tutoring", "facilitation"],
    "caregiving": ["care work", "elderly care", "patient care"],
    "first aid": ["cpr"],
    "security": ["security guard", "psira"],
    "cleaning": ["domestic work", "janitorial"],
    "gardening": ["landscaping", "groundskeeping"],
    "farming": ["agriculture", "agricultural work"],
    "sewing": ["tailoring", "seamstress"],
    "hairdressing": ["barbering", "beauty therapy"],
}


def _pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase.lower())
    # Word boundaries around the whole phrase, not each word inside it, so a
    # multi-word alias like "customer service" still matches as one unit.
    return re.compile(rf"(?<!\w){escaped}(?!\w)")


_COMPILED: list[tuple[str, re.Pattern[str]]] = [
    (skill, _pattern(alias))
    for skill, aliases in SKILL_VOCABULARY.items()
    for alias in [skill, *aliases]
]


def extract_required_skills(text: str) -> list[str]:
    lowered = text.lower()
    found: set[str] = set()
    for skill, pattern in _COMPILED:
        if skill not in found and pattern.search(lowered):
            found.add(skill)
    return sorted(found)

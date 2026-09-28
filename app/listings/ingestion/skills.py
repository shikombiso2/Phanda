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
    # Communication / soft skills (generic filler phrases excluded entirely --
    # see EXCLUDED_SKILLS below)
    "training": ["mentoring", "coaching"],
    "conflict resolution": [],
    "negotiation": [],
    "planning": ["organisational skills", "organizational skills"],
    # Concrete, decision-relevant -- confirmed live via investigation as
    # real, specifically stated requirements ("report writing skills",
    # "skilled in conducting research"), not vague praise any candidate
    # could claim. Distinct from EXCLUDED_SKILLS: those are generic filler
    # phrases with no checkable content; these name an actual, specific
    # ability someone either has evidence of or doesn't.
    "report writing": ["writing reports", "report compilation"],
    "research": ["research skills", "conducting research"],
    # Education level -- confirmed live via investigation: matric/grade-
    # level and qualification requirements are stated in plain, common
    # phrasings across real DPSA and Vacancy Update postings ("Grade 12
    # completed", "Grade 10 or ABET Level 4") and were being scanned but
    # silently dropped for lack of any matching vocabulary entry at all --
    # not a text-scanning gap, purely a coverage gap. Kept as separate
    # canonical entries, not aliases of one "education" tag, because they
    # are NOT interchangeable: a candidate whose CV states matric doesn't
    # satisfy a stated degree requirement, and treating them as one tag
    # would silently claim a match that isn't real.
    "matric": ["grade 12", "national senior certificate", "senior certificate", "nsc", "matriculation"],
    "grade 11": [],
    "grade 10": [],
    "abet level 4": ["abet level 1", "abet level 2", "abet level 3", "abet"],
    "diploma": ["national diploma"],
    "degree": ["bachelor's degree", "bachelors degree", "undergraduate degree"],
    "honours degree": ["honours", "honors"],
    "postgraduate": ["postgraduate degree", "postgraduate diploma", "master's degree", "masters degree", "phd", "doctorate"],
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


# Generic soft-skill filler phrases that are never extracted as a standalone
# skill, even if a future vocabulary entry or alias would otherwise match
# them -- these are things any candidate can claim, not a concrete, checkable
# ability someone could list as its own CV line item.
#
# "email"/"phone"/"tel"/"fax" belong to the same exclusion for a different
# reason: confirmed live against real listings that every occurrence of
# "email" in required_skills traced back to contact/application-instruction
# text ("email your CV to...", an enquiries contact's email address, "email
# address:" before an HR contact), never a genuine stated requirement like
# "email etiquette". The same contact-method noise applies to phone/tel/fax
# text, excluded pre-emptively even though none currently sit in
# SKILL_VOCABULARY, so a future alias addition can't reintroduce them.
EXCLUDED_SKILLS: frozenset[str] = frozenset(
    {
        "problem solving",
        "teamwork",
        "communication",
        "time management",
        "attention to detail",
        "work ethic",
        "leadership",
        "adaptability",
        "multitasking",
        "interpersonal skills",
        "hard working",
        "fast learner",
        "email",
        "phone",
        "tel",
        "fax",
    }
)


def _pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase.lower())
    # Word boundaries around the whole phrase, not each word inside it, so a
    # multi-word alias like "customer service" still matches as one unit.
    return re.compile(rf"(?<!\w){escaped}(?!\w)")


_COMPILED: list[tuple[str, re.Pattern[str]]] = [
    (skill, _pattern(alias))
    for skill, aliases in SKILL_VOCABULARY.items()
    if skill not in EXCLUDED_SKILLS
    for alias in [skill, *aliases]
]

# "X years experience" doesn't fit the literal-alias mechanism above at all
# -- the number varies, so there's no fixed phrase to list as an alias.
# Handled as its own regex instead of growing SKILL_VOCABULARY into a real
# pattern-matching engine for every entry.
#
# Deliberately a single flag, not a captured number: checked against
# app/recommendations/features.skill_compatibility() and
# build_match_explanation() first -- both only ever do set membership
# (skill in owned / skill not in owned) on canonical names, never a numeric
# comparison anywhere in the scoring pipeline. A specific "2" vs "5" years
# has nowhere downstream to be used yet, so capturing just "experience is
# required at all" is the right amount of signal for what this app checks
# today, not an under-implementation -- adding a number without a consumer
# for it would be complexity with no effect.
#
# Matches "2 years experience", "2 years' experience", "1-2 years of
# relevant work experience", "minimum of two (2) years' experience" (the
# parenthetical digit is what matches; the spelled-out word before it is
# not required). Does not match a number spelled out with no digit
# anywhere ("two years' experience") -- a known limitation of a keyword/
# regex approach, not attempted here.
_EXPERIENCE_YEARS_RE = re.compile(
    r"\(?\d+\)?(?:\s*(?:to|-|–)\s*\(?\d+\)?)?\+?\s*years?'?\s*"
    r"(?:of\s+)?(?:relevant\s+|working\s+|work\s+|prior\s+|previous\s+|post[- ]qualification\s+)*"
    r"experience",
    re.IGNORECASE,
)

EXPERIENCE_REQUIRED = "years of experience"


def extract_required_skills(text: str) -> list[str]:
    lowered = text.lower()
    found: set[str] = set()
    for skill, pattern in _COMPILED:
        if skill not in found and pattern.search(lowered):
            found.add(skill)
    if EXPERIENCE_REQUIRED not in EXCLUDED_SKILLS and _EXPERIENCE_YEARS_RE.search(lowered):
        found.add(EXPERIENCE_REQUIRED)
    return sorted(found)

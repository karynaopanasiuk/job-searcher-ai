"""
=== JOB SEARCH CONFIGURATION ===

Edit this file to customize the job search for YOUR profile.
Everything else works automatically.
"""

# ============================================================
# 1. YOUR PROFILE — fill in your details
# ============================================================

PROFILE = {
    "name": "Karyna Opanasiuk",
    "title": "Product Designer (UX/UI)",
    "experience_years": 6,
    "salary_min": 0,                     # salary is NOT a filter
    "salary_max": 0,
    "remote_only": True,
    "language": "uk",
}

# ============================================================
# 2. THE SIX RULES (the hard checks live in criteria.py; this text feeds the AI summary)
# ============================================================

TITLES = ["Senior Product designer", "Middle Product designer", "Product designer", "UX/UI Designer", "Middle UX/UI Designer", "Senior UX/UI Designer", "UX Designer", "Design Engineer"]

TARGET = [
    "Titles: " + ", ".join(TITLES),
    "Fully remote (remote is the only requirement on format)",
    "Works remotely as a sole proprietor; roles open worldwide, to EMEA, Europe or any non-US country are all fine",
    "Junior and intern roles are not wanted (rejected by title)",
    "6+ years of experience is fine: do not lower the score because the role asks for 6+ years or is senior",
]

NOT_INTERESTED = [
    "Roles only for people in the US (US-only, US residents, US work authorization required)",
    "Roles that require relocation",
    "Gaming and gambling companies (casino, betting, igaming, game studios, video games)",
    "Not remote (office or hybrid)",
]

# ============================================================
# 3. FIT CRITERIA — only these six rules count
# ============================================================

FIT_CRITERIA = """
| Rule | Passes | Fails |
|---|---|---|
| Format | Fully remote | Office, hybrid |
| Title | Senior Product designer, Product designer, UX/UI Designer, Senior UX/UI Designer, Design Engineer | Other roles |
| Location | Worldwide, EMEA, Europe, any non-US remote | US-only |
| Relocation | Not needed | Relocation required |
| Experience | Any, 6+ years is fine | (never a reason to reject) |
| Industry | Anything else | Gaming, gambling |
Salary, company type, domain, culture are NOT criteria.
"""

# ============================================================
# 4. YOUR KEY EXPERIENCE — for AI matching
# ============================================================

KEY_EXPERIENCE = [
    "6 years product design across startups and agencies (ideil, Phenomenon, Synthia.AI, Other.Land, Genue)",
    "Built a design system from scratch that became the foundation for 4+ products (components, tokens, documentation)",
    "Launched a paywall/monetization product end-to-end: discovery, requirements, admin panel, core features",
    "Redesigned onboarding and operational flows for the SIDES restaurant POS platform — cut support requests 5x",
    "Designed mobile subscription and payment flows, improving payment completion rates and engagement",
    "Led design of a healthcare platform admin panel; redesigned crypto transfer onboarding (fintech/Web3)",
    "Designed core AI platform flows at Synthia.AI: prompt guidance, response quality, guardrails for AI safety",
    "Strong in: UX research, usability testing, information architecture, accessibility, design QA, AI-assisted workflows",
    "Weaker/absent: production front-end coding, Adobe Creative Suite, motion design, A/B testing at scale, dedicated ecommerce",
]

# ============================================================
# 5. SEARCH KEYWORDS — what to search for on job boards
# ============================================================

SEARCH_KEYWORDS = [t.lower() for t in TITLES]

# Keywords that vacancy titles must contain (at least one)
TITLE_KEYWORDS = ["design", "designer", "ux", "ui", "дизайн", "дизайнер"]

# Titles containing any of these are skipped before spending an AI call on them
TITLE_EXCLUDE = [
    "graphic", "architect", "interior", "game", "3d", "motion", "video", "illustrat",
    "packaging", "fashion", "jewel", "ad designer", "brand designer", "creative services",
    "electronics", "mechanical", "structural", "industrial", "landscape", "hardware",
    "instructional", "lead generation", "marketing manager", "викладач", "графічн",
    "junior", "intern", "стажер",
]

# ============================================================
# 6. JOB BOARD URLS — customize search queries
# ============================================================

SOURCES = {
    # DOU and Djinni: everything these searches return goes to the board and to Telegram,
    # without profile filters or score cut-off. watch_ua.py polls them every 5 minutes.
    "Djinni": {
        "enabled": True,
        "searches": ["Senior Product designer", "Middle Product designer", "Product designer", "UX/UI Designer", "Middle UX/UI Designer", "Senior UX/UI Designer", "UX Designer", "Design Engineer"],
    },
    "DOU": {
        "enabled": True,
        "searches": ["Senior Product designer", "Middle Product designer", "Product designer", "UX/UI Designer", "Middle UX/UI Designer", "Senior UX/UI Designer", "UX Designer", "Design Engineer"],
    },
    "Work.ua": {
        "enabled": False,   # vacancy pages return 403 to scripts, so they can't be evaluated
        "url": "https://www.work.ua/en/jobs-ux+ui+designer/",
        "link_pattern": r'/en/jobs/\d+/',
    },
    # --- Foreign ---
    # Indeed, Glassdoor and Happy Monday are behind a Cloudflare challenge/captcha:
    # intentionally not scraped. Remote-job feeds below cover the same abroad market.
    "Wellfound": {
        "enabled": False,
        "urls": [
            "https://wellfound.com/role/r/product-designer",
            "https://wellfound.com/role/r/ux-designer",
            "https://wellfound.com/role/r/ui-ux-designer",
        ],
    },
    "Remotive": {
        "enabled": True,
        "url": "https://remotive.com/api/remote-jobs?category=design",
        "min_interval_hours": 6,   # Remotive asks for max ~4 requests/day
    },
    "RemoteOK": {
        "enabled": False,
        "url": "https://remoteok.com/api?tag=design",
        "min_interval_hours": 1,
    },
    # LinkedIn: public guest search only (no login, no challenge bypass). LinkedIn's terms
    # discourage automated access, so it is kept gentle: ~4 requests/hour, remote + last 24h only.
    "LinkedIn": {
        "enabled": False,
        "keywords": ["product designer", "ux ui designer", "ui ux designer"],
        "location": "Europe",
        "min_interval_hours": 1,
    },
    # Wellfound, RemoteOK and LinkedIn are switched off: they are not in the list of platforms to check.
    # UIUX Jobs Board: region pages, newest first. Plain HTTP works.
    "UIUXJobsBoard": {
        "enabled": True,
        "pages": ["remote-anywhere", "remote-emea", "remote-europe"],
        "per_page": 20,
        "min_interval_hours": 0,
    },
    # EU Remote Jobs refuses scripts (HTTP 520) but serves a normal browser, so it is read
    # through the Mac's own Google Chrome (headless, nothing disguised).
    "EUremoteJobs": {
        "enabled": True,
        "searches": ["product designer", "ux ui designer", "ux designer", "design engineer"],
        "max_new": 10,
        "min_interval_hours": 1,
    },
    "WeWorkRemotely": {
        "enabled": True,
        "url": "https://weworkremotely.com/categories/remote-design-jobs.rss",
        "min_interval_hours": 0,
    },
    # --- added for the six-rules setup; every check is a plain HTTP request ---
    "Workable": {"enabled": True, "pages": 2, "max_age_days": 7, "min_interval_hours": 0},
    "Layers": {"enabled": True, "min_interval_hours": 0},
    "TechTree": {"enabled": True, "url": "https://jobs.techtree.dev/?tp=67a38f89-bc11-4237-a6f8-cbcb6c74463d",
                 "min_interval_hours": 0},
    "RemoteJobsOrg": {"enabled": True, "searches": ["product designer", "ux ui designer", "ux designer", "design engineer"],
                      "min_interval_hours": 1},
    "NoFluffJobs": {"enabled": True, "pages": ["https://nofluffjobs.com/remote/design"], "min_interval_hours": 1},
    "WeLoveProduct": {"enabled": True, "min_interval_hours": 1},
    # Indeed, Glassdoor, Startup Jobs: blocked by a Cloudflare challenge / captcha, not bypassed.
    # They will come through e-mail alerts instead (see README).
}

# ============================================================
# 7. GROQ API KEY (free) — get yours at console.groq.com
# ============================================================

GROQ_API_KEY = ""  # Paste your key here, e.g. "gsk_abc123..."

# ============================================================
# 8. WEB SERVER
# ============================================================

WEB_PORT = 8080
WEB_HOST = "127.0.0.1"

# ============================================================
# 9. PAGE TITLE
# ============================================================

PAGE_TITLE = "Робота Product designer"

"""
The six rules a vacancy must pass, the same for every source.
Edit the lists below to change them; nothing else needs touching.

1. Remote only.
2. Title is one of: Senior Product designer, Middle Product designer, Product designer,
   UX/UI Designer, Middle / Senior UX/UI Designer, UX Designer, Design Engineer.
   Junior / Intern titles are rejected.
3. Only for people in the US  -> rejected.
4. Relocation required        -> rejected.
5. Years of experience are NOT a filter (6+ is fine, nothing is cut by seniority).
6. Gaming / gambling          -> rejected.

evaluate() returns (True, "") or (False, "short reason").
"""

import os
import re

# Extra regions (comma-separated, e.g. a country) that count as open to the candidate.
# Kept out of the code on purpose: set the EXTRA_REGIONS environment variable instead.
_EXTRA = [x.strip() for x in os.environ.get("EXTRA_REGIONS", "").split(",") if x.strip()]
EXTRA_REGIONS_ALT = "".join("|" + re.escape(x) for x in _EXTRA)


def mask(text: str) -> str:
    """Hide the extra region names from text that gets stored in the public state files."""
    for x in _EXTRA:
        text = re.sub(re.escape(x), "x", text, flags=re.I)
    return text

# --- 2. titles -----------------------------------------------------------
_SEP = r"\s*(?:/|-|&|and|\+|\s)\s*"
TITLE_PATTERNS = [
    r"product\s+designer",                 # also covers "Senior Product Designer"
    rf"ux{_SEP}ui\s+(?:product\s+)?designer",   # UX/UI designer, UX & UI designer, UX UI designer
    rf"ui{_SEP}ux\s+(?:product\s+)?designer",   # UI/UX designer
    r"(?<![a-z/])ux\s+designer",           # plain "UX designer" (Senior / Middle UX designer too)
    r"design\s+engineer",
    r"продуктов\w*\s+дизайнер",
    r"ux\s*/\s*ui\s+дизайнер",
    r"ui\s*/\s*ux\s+дизайнер",
]
_TITLE_RE = re.compile("|".join(f"(?:{p})" for p in TITLE_PATTERNS), re.I)

# --- 1. remote -----------------------------------------------------------
_REMOTE_RE = re.compile(
    r"(remote|віддал|worldwide|anywhere|telecommut|work from home|wfh|distributed|fully remote)", re.I)
_NOT_REMOTE_RE = re.compile(
    r"\b(hybrid|on-?site|in-?office|office[- ]based|гібрид|офіс)\b", re.I)

# --- 3. US only ----------------------------------------------------------
_US = r"(?:u\.?s\.?a?\.?|united states(?: of america)?)"
_US_ONLY_RE = re.compile(
    rf"(must (?:be )?(?:located|based|living|residing|reside|live)\s+(?:in|within)\s+(?:the\s+)?{_US}\b"
    rf"|{_US}[- ](?:residents?|citizens?|based)\s+only"
    rf"|(?:only|exclusively)\s+(?:open to\s+)?(?:candidates|applicants|residents)?\s*(?:located\s+)?(?:in|within)\s+(?:the\s+)?{_US}\b"
    rf"|(?:must|need to|required to)\s+(?:be\s+)?(?:legally\s+)?(?:authori[sz]ed|eligible)\s+to\s+work\s+in\s+(?:the\s+)?{_US}\b"
    rf"|authori[sz]ed to work in\s+(?:the\s+)?{_US}\b"
    rf"|{_US}\s+work\s+authori[sz]ation"
    rf"|\b{_US}\s+only\b"
    rf"|location\s*[:\-]\s*(?:remote\s*[,\-(]?\s*)?{_US}\s*(?:only)?\s*(?:\)|\n|$|\.)"
    rf"|remote\s*[\(\-,]\s*{_US}\s*(?:only)?\s*\)?\s*$"
    rf"|(?:eligible|authori[sz]ed)\s+to\s+work\s+in\s+the\s+{_US}\b)", re.I | re.M)
_GLOBAL_RE = re.compile(
    r"(worldwide|anywhere in the world|work from anywhere|global(?:ly)?\s+remote|emea|europe|"
    r"outside (?:of )?the (?:us|u\.s\.|united states)|any country|ukrain|mena|cet\b|\beu\b" + EXTRA_REGIONS_ALT + ")", re.I)

_GLOBAL_STRONG_RE = re.compile(
    r"(worldwide|anywhere in the world|work from anywhere|emea\b|outside (?:of )?the (?:us|u\.s\.|united states))", re.I)

# --- 4. relocation -------------------------------------------------------
_RELOC_RE = re.compile(
    r"((?:must|required to|need to|have to|willing to|ready to|able to|open to|should be willing to)\s+relocat"
    r"|relocation\s+(?:is\s+)?(?:required|mandatory|necessary)"
    r"|(?:requires?|requiring)\s+relocation"
    r"|relocat\w*\s+to\s+(?:our|the)\s+(?:office|hq|headquarters|country)"
    r"|переїзд\s+(?:обов|до)|потрібен\s+релокейт)", re.I)
_RELOC_TITLE_RE = re.compile(r"relocat|релокейт", re.I)

# --- 6. gaming / gambling ------------------------------------------------
_GAMING_RE = re.compile(
    r"(casino|gambl|sports\s?betting|\bbetting\s+(?:platform|company|app|operator|brand)|igaming|i-gaming|"
    r"sportsbook|\bpoker\b|online\s+slots?|slot\s+(?:machine|game)s?|\bbookmaker|\blottery\b|"
    r"gamedev|game\s+dev(?:elop\w*)?|game\s+(?:studio|company|industry|publisher)|video\s+games?|mobile\s+games?|"
    r"\bgaming\b|\besports?\b|\bgame\s+(?:designer|ui|artist|art))",
    re.I)


# "Design Engineer" also names hardware / chip / mechanical jobs; those are not product design.
_NOT_SOFTWARE_RE = re.compile(
    r"(asic|fpga|physical|mechanical|electrical|electronic|hardware|verification|rtl|analog|mixed[- ]signal|"
    r"civil|structural|piping|hvac|process|chip|semiconductor|vlsi|manufactur|cad\b|bim\b|valve|pcb|firmware|"
    r"embedded|power|thermal|packaging|tooling|automotive)", re.I)

# Location field that names only the US (a structured fact: it beats any "worldwide" word in the text)
_US_LOCATION_ONLY_RE = re.compile(
    rf"^\s*(?:remote\s*[,\-(/]?\s*)?(?:{_US}(?:\s*,\s*{_US})*)\s*\)?\s*(?:only)?\s*$", re.I)


_JUNIOR_RE = re.compile(r"(junior|\bjr\.?\b|intern(?:ship)?\b|trainee|стажер|стажист|джуніор|джун\b)", re.I)


def title_ok(title: str) -> bool:
    t = title or ""
    if not _TITLE_RE.search(t):
        return False
    if _JUNIOR_RE.search(t):
        return False
    if re.search(r"design\s+engineer", t, re.I) and not re.search(r"product\s+designer", t, re.I) \
            and _NOT_SOFTWARE_RE.search(t):
        return False
    return True


def evaluate(title: str, text: str = "", location: str = "", remote_hint=None):
    """remote_hint: True when the board itself only lists remote jobs (or the card says remote)."""
    body = (text or "")[:6000]
    head = f"{title}\n{location}\n{body[:700]}"
    whole = f"{title}\n{location}\n{body}"

    if not title_ok(title):
        return False, "назва не з вашого списку"

    # 6. gaming / gambling — title, location, first 3000 characters (company intro lives there)
    m = _GAMING_RE.search(f"{title}\n{body[:3000]}")
    if m:
        return False, f"gaming/gambling ({m.group(0).strip().lower()})"

    # 4. relocation
    if _RELOC_TITLE_RE.search(title) and not re.search(r"remote|віддал", title, re.I):
        return False, "потрібен релокейт (у назві)"
    m = _RELOC_RE.search(whole)
    if m:
        return False, f"релокейт ({m.group(0).strip().lower()})"

    # 1. remote
    if _NOT_REMOTE_RE.search(f"{title}\n{location}") and not _REMOTE_RE.search(f"{title}\n{location}"):
        return False, "не remote (офіс/гібрид)"
    if not remote_hint and not _REMOTE_RE.search(head):
        return False, "не видно, що remote"

    # 3. US only
    if location and _US_LOCATION_ONLY_RE.match(location.strip()):
        return False, "лише США"
    if (_US_ONLY_RE.search(whole) and not _GLOBAL_RE.search(f"{title}\n{location}")
            and not _GLOBAL_STRONG_RE.search(whole)):
        return False, "лише США"

    return True, ""

#!/usr/bin/env python3
"""
Check multiple job boards for new UI/UX vacancies.
If found, analyze with Groq and add to vacancies.md.
Run via cron every 2 hours.
"""

import os
import re
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
import time
import html as htmllib
from itertools import zip_longest
import xml.etree.ElementTree as ET
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
MD_FILE = os.path.join(BASE_DIR, "vacancies.md")
ANALYSES_FILE = os.path.join(BASE_DIR, "analyses.json")
LOG_FILE = os.path.join(BASE_DIR, "check.log")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Load config — keywords and sources come from config.py
try:
    from config import TITLE_KEYWORDS, SOURCES
except ImportError:
    TITLE_KEYWORDS = ['design', 'ux', 'ui', 'product design', 'дизайн']
    SOURCES = {}
try:
    from config import TITLE_EXCLUDE
except ImportError:
    TITLE_EXCLUDE = []

KEYWORDS = [k.lower() for k in TITLE_KEYWORDS]

import criteria  # noqa: E402  (the six rules, shared by every source)

SKIPPED_FILE = os.path.join(BASE_DIR, "skipped.json")


def _load_skipped() -> set:
    try:
        with open(SKIPPED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def skip(url: str) -> None:
    """Remember a page that failed the title rule, so it is not downloaded again every 10 minutes."""
    s = _load_skipped()
    url = criteria.mask(url)
    if url not in s:
        s.add(url)
        with open(SKIPPED_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(s)[-5000:], f)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_html(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        log(f"  Fetch error for {url}: {e}")
        return ""


def get_existing_urls() -> set:
    if not os.path.exists(MD_FILE):
        return set()
    with open(MD_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    urls = set(re.findall(r'\((https?://[^)]+)\)', content))
    # Low-scored vacancies are analyzed but not written to the md file; count them as
    # known too, otherwise they get re-fetched and re-scored on every scheduled run.
    if os.path.exists(ANALYSES_FILE):
        try:
            with open(ANALYSES_FILE, "r", encoding="utf-8") as f:
                urls |= set(json.load(f).keys())
        except ValueError:
            pass
    return urls | _load_skipped()


def is_relevant(title: str) -> bool:
    """Title must be one of the five names (see criteria.py)."""
    return criteria.title_ok(title)


# ============================================================
# PARSERS FOR EACH JOB BOARD
# ============================================================

UA_DEFAULT_SEARCHES = ["Senior Product designer", "Middle Product designer", "Product designer", "UX/UI Designer", "Middle UX/UI Designer", "Senior UX/UI Designer", "UX Designer", "Design Engineer"]

# DOU and Djinni take everything their search returns — no profile criteria, no junior/game
# exclusions, no score cut-off. Only search noise is dropped: Djinni's search also returns
# e.g. "Senior Product Manager", so the title must at least mention design / UX / UI.
class _DesignTitle:
    search = staticmethod(lambda t: criteria.title_ok(t))


_DESIGN_TITLE = _DesignTitle()

_UA_MONTHS = {"січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
              "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12}


def _ua_searches(name: str) -> list:
    return SOURCES.get(name, {}).get("searches") or UA_DEFAULT_SEARCHES


def _dou_date(text: str):
    """'15 листопада' / '15 листопада 2025' -> datetime (most recent past date if no year)."""
    m = re.match(r"\s*(\d{1,2})\s+([а-яіїєґ']+)(?:\s+(\d{4}))?", text or "", re.I)
    if not m or m.group(2).lower() not in _UA_MONTHS:
        return None
    day, month = int(m.group(1)), _UA_MONTHS[m.group(2).lower()]
    now = datetime.now()
    year = int(m.group(3)) if m.group(3) else now.year
    try:
        dt = datetime(year, month, day)
    except ValueError:
        return None
    if not m.group(3) and dt > now:
        dt = dt.replace(year=year - 1)
    return dt


def _djinni_id(url: str):
    m = re.search(r"djinni\.co/jobs/(\d+)", url or "")
    return m.group(1) if m else None


def check_djinni():
    """Djinni.co — every result of the configured searches (title search, newest first).
    Data comes from the JobPosting JSON-LD that Djinni embeds in the search page."""
    log("Checking Djinni...")
    existing = get_existing_urls()
    known_ids = {_djinni_id(u) for u in existing if "djinni.co" in u}
    results, seen = [], set()

    for term in _ua_searches("Djinni"):
        q = urllib.parse.urlencode({"all_keywords": term, "search_type": "basic-search"})
        page = fetch_html(f"https://djinni.co/jobs/?{q}")
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
            try:
                data = json.loads(block)
            except ValueError:
                continue
            for job in (data if isinstance(data, list) else [data]):
                if not isinstance(job, dict) or job.get("@type") != "JobPosting":
                    continue
                url = (job.get("url") or "").split("?")[0].rstrip("/")   # stored without slash
                jid = _djinni_id(url)
                title = _plain(job.get("title"))
                if not jid or jid in seen or jid in known_ids or not _DESIGN_TITLE.search(title):
                    continue
                seen.add(jid)
                company = _plain((job.get("hiringOrganization") or {}).get("name"))
                remote = "віддалено" if job.get("jobLocationType") == "TELECOMMUTE" else ""
                salary = ""
                base = job.get("baseSalary") or {}
                val = base.get("value") if isinstance(base, dict) else None
                if isinstance(val, dict) and (val.get("minValue") or val.get("maxValue")):
                    lo, hi = val.get("minValue"), val.get("maxValue")
                    salary = f"${lo}–{hi}" if lo and hi and lo != hi else f"${lo or hi}"
                text = (f"{title}\nCompany: {company}\nLocation: {remote or 'see page'}\n"
                        f"Salary: {salary or 'not listed'}\n\n{_plain(job.get('description'))}")[:5000]
                results.append({
                    "title": f"{title} — {company}" if company else title,
                    "url": url, "section": "Djinni.co", "text": text,
                    "posted": _parse_dt(job.get("datePosted")), "no_filter": True,
                    "remote_hint": bool(remote), "location": remote,
                    "meta": " · ".join(x for x in (company, salary, remote) if x),
                })
        time.sleep(1)

    log(f"  Found {len(results)} new on Djinni")
    return results


def check_dou():
    """DOU.ua — every result of the configured searches (newest first)."""
    log("Checking DOU...")
    existing = get_existing_urls()
    results, seen = [], set()

    for term in _ua_searches("DOU"):
        page = fetch_html("https://jobs.dou.ua/vacancies/?" + urllib.parse.urlencode({"search": term}))
        for card in re.findall(r'<li class="l-vacancy[^"]*">(.*?)</li>', page, re.S):
            m = re.search(r'<a class="vt" href="(https://jobs\.dou\.ua/companies/[^/]+/vacancies/\d+/)[^"]*"\s*>(.*?)</a>',
                          card, re.S)
            if not m:
                continue
            url, title = m.group(1), _plain(m.group(2))
            if url in seen or url in existing or not _DESIGN_TITLE.search(title):
                continue
            seen.add(url)
            company = _plain((re.search(r'class="company"[^>]*>(.*?)</a>', card, re.S) or [0, ""])[1])
            cities = _plain((re.search(r'class="cities[^"]*">(.*?)</span>', card, re.S) or [0, ""])[1])
            salary = _plain((re.search(r'class="salary">(.*?)</span>', card, re.S) or [0, ""])[1])
            date_txt = _plain((re.search(r'class="date">(.*?)</div>', card, re.S) or [0, ""])[1])
            info = _plain((re.search(r'class="sh-info">(.*?)</div>', card, re.S) or [0, ""])[1])
            text = (f"{title}\nCompany: {company}\nLocation: {cities or 'see page'}\n"
                    f"Salary: {salary or 'not listed'}\n\n{info}")
            results.append({
                "title": f"{title} — {company}" if company else title,
                "url": url, "section": "DOU.ua",
                # the list only shows a teaser; analysis fetches the full page itself
                "text": None, "teaser": text,
                "posted": _dou_date(date_txt), "no_filter": True, "location": cities,
                "meta": " · ".join(x for x in (company, salary, cities) if x),
            })
        time.sleep(1)

    log(f"  Found {len(results)} new on DOU")
    return results


def check_workua():
    """Work.ua — Ukrainian job board."""
    log("Checking Work.ua...")
    url = SOURCES.get("Work.ua", {}).get("url", "https://www.work.ua/en/jobs-ui+ux+designer/")
    html = fetch_html(url)
    if not html:
        return []

    existing = get_existing_urls()
    results = []

    # Pattern: <a href="/en/jobs/ID/" ...>TITLE</a>
    for m in re.finditer(r'<a[^>]*href="(/en/jobs/(\d+)/)"[^>]*>\s*([^<]{10,})', html):
        path = m.group(1)
        url = f"https://www.work.ua{path}"
        title = m.group(3).strip()
        if url in existing or not is_relevant(title):
            continue
        results.append({"title": title, "url": url, "section": "Work.ua"})

    log(f"  Found {len(results)} new on Work.ua")
    return results


# ---------- Foreign sources ----------
# Indeed, Glassdoor and Happy Monday sit behind a Cloudflare challenge/captcha and are
# deliberately NOT scraped. The sources below expose public data meant to be read.

_REGION_BAD = re.compile(
    r"\b(usa|u\.s\.|us only|us-based|united states|canada|north america|latam|latin america|"
    r"brazil|india|apac|australia|new zealand|philippines|singapore|uk only)\b", re.I)
_REGION_GOOD = re.compile(
    r"(worldwide|anywhere|global|europe|emea|ukrain|mena|middle east|\beu\b|cet" + criteria.EXTRA_REGIONS_ALT + ")", re.I)


def _region_ok(location: str) -> bool:
    """Drop listings restricted to regions the candidate can't work from."""
    loc = location or ""
    return not (_REGION_BAD.search(loc) and not _REGION_GOOD.search(loc))


def _parse_dt(value):
    """Best-effort posting date from an ISO string, RFC-822 string or unix timestamp."""
    if not value:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value))
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(str(value)).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        return None


def _plain(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def _fetch_json(url: str):
    raw = fetch_html(url)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        log(f"  Not JSON: {url}")
        return None


def check_wellfound():
    """Wellfound — startup jobs. Data is embedded in the page as __NEXT_DATA__."""
    log("Checking Wellfound...")
    pages = SOURCES.get("Wellfound", {}).get("urls") or [
        "https://wellfound.com/role/r/product-designer",
        "https://wellfound.com/role/r/ux-designer",
        "https://wellfound.com/role/r/ui-ux-designer",
    ]
    existing = get_existing_urls()
    cutoff = time.time() - 45 * 86400
    results, seen = [], set()

    for page in pages:
        page_html = fetch_html(page)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html or "", re.S)
        if not m:
            log(f"  Wellfound: no data on {page} (blocked or layout changed)")
            continue
        try:
            data = json.loads(m.group(1))["props"]["pageProps"]["apolloState"]["data"]
        except (KeyError, ValueError) as e:
            log(f"  Wellfound: unexpected structure ({e})")
            continue

        company_of = {}
        for key, val in data.items():
            if key.startswith("StartupResult:") and isinstance(val, dict):
                for jid in set(re.findall(r"JobListingSearchResult:(\d+)", json.dumps(val))):
                    company_of.setdefault(jid, val.get("name", ""))

        for key, job in data.items():
            if not key.startswith("JobListingSearchResult:") or not isinstance(job, dict):
                continue
            jid = key.split(":")[1]
            title = job.get("title") or job.get("primaryRoleTitle") or ""
            url = f"https://wellfound.com/jobs/{jid}-{job.get('slug') or 'job'}"
            if url in existing or url in seen or not is_relevant(title) or not job.get("remote"):
                continue
            try:
                if int(job.get("liveStartAt") or 0) < cutoff:
                    continue
            except (TypeError, ValueError):
                pass
            accepted = ", ".join(job.get("acceptedRemoteLocationNames") or [])
            if not _region_ok(accepted):
                continue
            seen.add(url)
            company = company_of.get(jid, "")
            text = (
                f"{title}\nCompany: {company}\nCompensation: {job.get('compensation') or 'not listed'}\n"
                f"Location: {', '.join(job.get('locationNames') or [])} | remote OK from: {accepted or 'unspecified'}\n"
                f"Job type: {job.get('jobType')}\n"
                f"Experience: {job.get('yearsExperienceMin')}-{job.get('yearsExperienceMax')} years\n\n"
                f"{job.get('description') or ''}"
            )[:5000]
            results.append({"title": f"{title} — {company}" if company else title,
                            "url": url, "section": "Wellfound", "text": text,
                            "posted": _parse_dt(job.get("liveStartAt"))})
        time.sleep(2)

    log(f"  Found {len(results)} new on Wellfound")
    return results


def check_remotive():
    """Remotive public API (asks for max ~4 requests/day — see min_interval_hours)."""
    log("Checking Remotive...")
    url = SOURCES.get("Remotive", {}).get("url", "https://remotive.com/api/remote-jobs?category=design")
    data = _fetch_json(url)
    if not data:
        return []
    existing = get_existing_urls()
    results = []
    for j in data.get("jobs", []):
        title, link = j.get("title", ""), j.get("url", "")
        loc = j.get("candidate_required_location", "")
        if not link or link in existing or not is_relevant(title) or not _region_ok(loc):
            continue
        text = (f"{title}\nCompany: {j.get('company_name')}\nLocation: {loc}\n"
                f"Salary: {j.get('salary') or 'not listed'}\nType: {j.get('job_type')}\n\n"
                f"{_plain(j.get('description'))}")[:5000]
        results.append({"title": f"{title} — {j.get('company_name')}", "url": link,
                        "section": "Remotive", "text": text, "remote_hint": True, "location": loc,
                        "posted": _parse_dt(j.get("publication_date"))})
    log(f"  Found {len(results)} new on Remotive")
    return results


def check_remoteok():
    """RemoteOK public API (free to use; links point back to RemoteOK as required)."""
    log("Checking RemoteOK...")
    url = SOURCES.get("RemoteOK", {}).get("url", "https://remoteok.com/api?tag=design")
    data = _fetch_json(url)
    if not data:
        return []
    existing = get_existing_urls()
    results = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first element is a legal notice
        title, link, loc = j.get("position", ""), j.get("url", ""), j.get("location", "")
        if not link or link in existing or not is_relevant(title) or not _region_ok(loc):
            continue
        sal = f"${j.get('salary_min')}-{j.get('salary_max')}" if j.get("salary_min") else "not listed"
        text = (f"{title}\nCompany: {j.get('company')}\nLocation: {loc or 'unspecified'}\n"
                f"Salary: {sal}\nTags: {', '.join(j.get('tags') or [])}\n\n"
                f"{_plain(j.get('description'))}")[:5000]
        results.append({"title": f"{title} — {j.get('company')}", "url": link,
                        "section": "RemoteOK", "text": text,
                        "posted": _parse_dt(j.get("date") or j.get("epoch"))})
    log(f"  Found {len(results)} new on RemoteOK")
    return results


def check_wwr():
    """We Work Remotely — design category RSS feed."""
    log("Checking WeWorkRemotely...")
    url = SOURCES.get("WeWorkRemotely", {}).get(
        "url", "https://weworkremotely.com/categories/remote-design-jobs.rss")
    raw = fetch_html(url)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        log(f"  WWR feed parse error: {e}")
        return []
    existing = get_existing_urls()
    results = []
    for item in root.iter("item"):
        full_title = (item.findtext("title") or "").strip()      # "Company: Role"
        link = (item.findtext("link") or "").strip()
        region = (item.findtext("region") or "").strip()
        title = full_title.split(":", 1)[1].strip() if ":" in full_title else full_title
        if not link or link in existing or not is_relevant(title) or not _region_ok(region):
            continue
        text = (f"{full_title}\nRegion: {region}\nSkills: {item.findtext('skills') or ''}\n\n"
                f"{_plain(item.findtext('description'))}")[:5000]
        results.append({"title": full_title, "url": link, "section": "WeWorkRemotely", "text": text, "remote_hint": True, "location": region,
                        "posted": _parse_dt(item.findtext("pubDate"))})
    log(f"  Found {len(results)} new on WeWorkRemotely")
    return results

def _uiux_text(page: str) -> str:
    """Vacancy description on a UIUX Jobs Board page: from 'is hiring' to 'People also viewed'."""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S)
    m = re.search(r"is hiring(.*?)(People also viewed|Related jobs)", body, re.S)
    body = m.group(1) if m else body
    body = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", body)
    body = htmllib.unescape(re.sub(r"<[^>]+>", " ", body))
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", body)).strip()


def check_uiux():
    """UIUX Jobs Board — region pages (Anywhere, EMEA, Europe, plus any in UIUX_EXTRA_PAGES), newest first.
    Plain HTTP works here. Each new job page carries a JobPosting JSON-LD plus the full text."""
    log("Checking UIUX Jobs Board...")
    cfg = SOURCES.get("UIUXJobsBoard", {})
    pages = list(cfg.get("pages") or ["remote-anywhere", "remote-emea", "remote-europe"])
    pages += [p.strip() for p in os.environ.get("UIUX_EXTRA_PAGES", "").split(",") if p.strip() and p.strip() not in pages]
    per_page = cfg.get("per_page", 20)   # newest N of each region page
    existing = get_existing_urls()
    known_ids = {m.group(1) for u in existing for m in [re.search(r"uiuxjobsboard\.com/job/(\d+)", u)] if m}
    results, seen = [], set()
    for region in pages:
        listing = fetch_html(f"https://uiuxjobsboard.com/design-jobs/{region}")
        paths = list(dict.fromkeys(re.findall(r'href="(/job/\d+-[^"#?]+)"', listing)))[:per_page]
        for path in paths:
            jid = re.match(r"/job/(\d+)", path).group(1)
            if jid in known_ids or jid in seen:
                continue
            seen.add(jid)
            url = "https://uiuxjobsboard.com" + path
            page = fetch_html(url)
            title, company, posted = "", "", None
            for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
                try:
                    d = json.loads(block)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("@type") == "JobPosting":
                    title = _plain(d.get("title"))
                    company = _plain((d.get("hiringOrganization") or {}).get("name"))
                    posted = _parse_dt(d.get("datePosted"))
            if not title or not is_relevant(title):
                skip(url)
                continue
            text = f"{title}\nCompany: {company}\nRegion: {region.replace('remote-', '')}\n\n{_uiux_text(page)}"[:5000]
            results.append({"title": f"{title} — {company}" if company else title, "url": url,
                            "section": "UIUXJobsBoard", "text": text, "posted": posted,
                            "remote_hint": True, "location": region.replace("remote-", "")})
            time.sleep(0.7)
    log(f"  Found {len(results)} new on UIUX Jobs Board")
    return results


def _chrome_html(url: str, wait_ms: int = 10000) -> str:
    """Rendered page from a regular headless Google Chrome (the Mac's own, nothing patched or disguised).
    Some sites answer plain scripts with an error but serve a normal browser."""
    import shutil
    import subprocess
    import tempfile
    chrome = (os.environ.get("CHROME_BIN") or SOURCES.get("EUremoteJobs", {}).get("chrome")
              or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not os.path.exists(chrome):
        chrome = shutil.which("google-chrome") or shutil.which("chromium") or chrome
    if not os.path.exists(chrome):
        log("  Chrome not found, skipping")
        return ""
    profile = tempfile.mkdtemp(prefix="jobs-chrome-")
    try:
        r = subprocess.run([chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
                            f"--virtual-time-budget={wait_ms}", "--dump-dom", url],
                           capture_output=True, text=True, timeout=int(os.environ.get("CHROME_TIMEOUT", "120")))
        return r.stdout
    except (subprocess.TimeoutExpired, OSError) as e:
        log(f"  Chrome error for {url}: {e}")
        return ""
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def check_euremotejobs():
    """EU Remote Jobs — the site refuses scripts (HTTP 520) but serves a real browser, so read it through Chrome.
    Gentle: a few search pages plus up to `max_new` job pages per run."""
    log("Checking EU Remote Jobs...")
    cfg = SOURCES.get("EUremoteJobs", {})
    searches = cfg.get("searches") or ["product designer", "ux ui designer", "ux designer"]
    max_new = cfg.get("max_new", 10)
    existing = get_existing_urls()
    found = {}
    for term in searches:
        page = _chrome_html("https://euremotejobs.com/jobs/?" + urllib.parse.urlencode({"search_keywords": term}))
        for m in re.finditer(r'<a[^>]+href="(https://euremotejobs\.com/job/[^"#?]+/?)"[^>]*>(.*?)</a>', page, re.S):
            url = m.group(1)
            if not url.endswith("/"):
                url += "/"
            if url not in existing and url not in found:
                found[url] = _plain(m.group(2))
    results = []
    for url, link_text in list(found.items())[:max_new]:
        page = _chrome_html(url)
        if not page:
            continue
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        title = _plain(h1.group(1)) if h1 else link_text
        if not title or not is_relevant(title):
            skip(url)
            continue
        m = re.search(r'<div class="job_description"[^>]*>(.*?)</div>\s*(?:<div class="job_application|<section|<footer)', page, re.S)
        body = _plain((m.group(1) if m else re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S)))
        posted = None
        dm = re.search(r'"datePosted"\s*:\s*"([^"]+)"', page)
        if dm:
            posted = _parse_dt(dm.group(1))
        body = body.rsplit("Post a job", 1)[-1].strip()   # drop the site menu in front of the ad
        results.append({"title": title, "url": url, "section": "EURemoteJobs", "remote_hint": True,
                        "text": f"{title}\n\n{body}"[:5000], "posted": posted})
        time.sleep(1)
    log(f"  Found {len(results)} new on EU Remote Jobs")
    return results


# ---------------- new platforms (all remote-only or filtered by title first) ----------------

def _ld_job(page: str):
    """First JobPosting object from the JSON-LD blocks of a page (also looks inside @graph)."""
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            d = json.loads(block)
        except ValueError:
            continue
        stack = d if isinstance(d, list) else [d]
        while stack:
            x = stack.pop(0)
            if isinstance(x, dict):
                if x.get("@type") == "JobPosting":
                    return x
                if isinstance(x.get("@graph"), list):
                    stack.extend(x["@graph"])
    return None


def check_workable():
    """Workable's public job search (jobs.workable.com), remote jobs only, one query per title."""
    log("Checking Workable...")
    cfg = SOURCES.get("Workable", {})
    searches = cfg.get("searches") or UA_DEFAULT_SEARCHES
    pages = cfg.get("pages", 2)
    max_age = cfg.get("max_age_days", 30)
    existing = get_existing_urls()
    results, seen = [], set()
    for term in searches:
        token = ""
        for _ in range(pages):
            q = {"query": term, "workplace": "remote"}
            if token:
                q["pageToken"] = token
            data = _fetch_json("https://jobs.workable.com/api/v1/jobs?" + urllib.parse.urlencode(q))
            if not data:
                break
            for j in data.get("jobs", []):
                url, title = j.get("url", ""), _plain(j.get("title"))
                if not url or url in seen or url in existing or not is_relevant(title):
                    continue
                created = _parse_dt(j.get("created"))
                if created and (datetime.now() - created).days > max_age:
                    continue
                seen.add(url)
                company = _plain((j.get("company") or {}).get("title"))
                locs = ", ".join(x for x in (j.get("locations") or []) if x != "TELECOMMUTE")
                loc = locs or (j.get("location") or {}).get("countryName") or ""
                desc = _plain(" ".join([j.get("description") or "", j.get("requirementsSection") or ""]))
                text = f"{title}\nCompany: {company}\nLocation: {loc}\nRemote\n\n{desc}"[:5000]
                results.append({"title": f"{title} — {company}" if company else title, "url": url,
                                "section": "Workable", "text": text, "posted": created,
                                "remote_hint": True, "location": loc})
            token = data.get("nextPageToken") or ""
            if not token:
                break
            time.sleep(1)
        time.sleep(1)
    log(f"  Found {len(results)} new on Workable")
    return results


def check_layers():
    """Layers (layers.to/jobs) — design jobs; title is in the link, so only matching pages are opened."""
    log("Checking Layers...")
    existing = get_existing_urls()
    listing = fetch_html("https://layers.to/jobs")
    paths = list(dict.fromkeys(re.findall(r'href="(/jobs/c[a-z0-9]{20,}-[^"#?]+)"', listing)))
    results = []
    for path in paths:
        url = "https://layers.to" + path
        slug_title = path.split("-", 1)[1].replace("-", " ") if "-" in path else ""
        if url in existing or not is_relevant(slug_title):
            continue
        page = fetch_html(url)
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        title = _plain(h1.group(1)) if h1 else slug_title
        main = re.search(r"<main.*?</main>", page, re.S)
        body = _plain(main.group(0) if main else page)
        results.append({"title": title, "url": url, "section": "Layers",
                        "text": f"{title}\n\n{body}"[:5000], "posted": None})
        time.sleep(1)
    log(f"  Found {len(results)} new on Layers")
    return results


def check_techtree():
    """TechTree job board (jobs.techtree.dev) — the card text starts with the title, JobPosting JSON-LD on the page."""
    log("Checking TechTree...")
    cfg = SOURCES.get("TechTree", {})
    base = cfg.get("url", "https://jobs.techtree.dev/")
    existing = get_existing_urls()
    listing = fetch_html(base)
    results = []
    for m in re.finditer(r'<a[^>]+href="(/job/[0-9a-f-]{36})(?:\?[^"]*)?"[^>]*>(.*?)</a>', listing, re.S):
        url = "https://jobs.techtree.dev" + m.group(1)
        card = _plain(m.group(2))
        if url in existing or not is_relevant(card):
            continue
        page = fetch_html(url)
        job = _ld_job(page) or {}
        title = _plain(job.get("title")) or card
        if not is_relevant(title):
            skip(url)
            continue
        loc = job.get("jobLocation")
        loc = (loc.get("address") if isinstance(loc, dict) else "") or ""
        company = _plain((job.get("hiringOrganization") or {}).get("name"))
        text = (f"{title}\nCompany: {company}\nLocation: {loc}\n\n{_plain(job.get('description'))}\n\n{card}")[:5000]
        results.append({"title": f"{title} — {company}" if company else title, "url": url,
                        "section": "TechTree", "text": text, "posted": _parse_dt(job.get("datePosted")),
                        "location": str(loc)})
        time.sleep(1)
    log(f"  Found {len(results)} new on TechTree")
    return results


def check_remotejobs_org():
    """remotejobs.org — search pages list /remote-jobs/<slug>; each page has JobPosting JSON-LD."""
    log("Checking remotejobs.org...")
    cfg = SOURCES.get("RemoteJobsOrg", {})
    searches = cfg.get("searches") or ["product designer", "ux ui designer", "design engineer"]
    existing = get_existing_urls()
    found = {}
    for term in searches:
        page = fetch_html("https://remotejobs.org/remote-jobs?" + urllib.parse.urlencode({"q": term}))
        for path in re.findall(r'href="(/remote-jobs/[a-z0-9-]+)"', page):
            slug = path.rsplit("/", 1)[1]
            if slug.startswith("product-designer") or is_relevant(slug.replace("-", " ")):
                found.setdefault("https://remotejobs.org" + path, slug)
        time.sleep(1)
    results = []
    for url in found:
        if url in existing:
            continue
        page = fetch_html(url)
        job = _ld_job(page) or {}
        title = _plain(job.get("title"))
        if not title or not is_relevant(title):
            skip(url)
            continue
        company = _plain((job.get("hiringOrganization") or {}).get("name"))
        req = job.get("applicantLocationRequirements")
        reqs = [req] if isinstance(req, dict) else (req or [])
        loc = ", ".join(str(r.get("name")) for r in reqs if isinstance(r, dict) and r.get("name"))
        text = f"{title}\nCompany: {company}\nLocation: {loc}\nRemote\n\n{_plain(job.get('description'))}"[:5000]
        results.append({"title": f"{title} — {company}" if company else title, "url": url,
                        "section": "RemoteJobsOrg", "text": text, "posted": _parse_dt(job.get("datePosted")),
                        "remote_hint": True, "location": loc})
        time.sleep(1)
    log(f"  Found {len(results)} new on remotejobs.org")
    return results


def check_nofluff():
    """No Fluff Jobs — remote design category. robots.txt allows it; kept gentle (one list page,
    only pages whose title already matches are opened)."""
    log("Checking No Fluff Jobs...")
    cfg = SOURCES.get("NoFluffJobs", {})
    pages = cfg.get("pages") or ["https://nofluffjobs.com/remote/design"]
    existing = get_existing_urls()
    results = []
    for list_url in pages:
        listing = fetch_html(list_url)
        for path in dict.fromkeys(re.findall(r'href="(/job/[^"#?]+)"', listing)):
            slug = path.rsplit("/", 1)[1]
            url = "https://nofluffjobs.com" + path
            if url in existing or not is_relevant(slug.replace("-", " ")):
                continue
            page = fetch_html(url)
            job = _ld_job(page) or {}
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
            title = _plain(job.get("title")) or (_plain(h1.group(1)) if h1 else slug)
            if not is_relevant(title):
                skip(url)
                continue
            body = _plain(job.get("description")) or _plain(re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S))
            results.append({"title": title, "url": url, "section": "NoFluffJobs",
                            "text": f"{title}\nRemote\n\n{body}"[:5000],
                            "posted": _parse_dt(job.get("datePosted")), "remote_hint": True})
            time.sleep(1)
    log(f"  Found {len(results)} new on No Fluff Jobs")
    return results


def check_weloveproduct():
    """WeLoveProduct — mostly product-manager jobs; only design titles pass the title rule."""
    log("Checking WeLoveProduct...")
    existing = get_existing_urls()
    listing = fetch_html("https://weloveproduct.co/")
    results = []
    for path in dict.fromkeys(re.findall(r'href="(/jobs/[a-z0-9-]+)"', listing)):
        url = "https://weloveproduct.co" + path
        slug = path.rsplit("/", 1)[1].rsplit("-", 1)[0].replace("-", " ")
        if url in existing or not is_relevant(slug):
            continue
        page = fetch_html(url)
        job = _ld_job(page) or {}
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        title = _plain(job.get("title")) or (_plain(h1.group(1)) if h1 else slug)
        if not is_relevant(title):
            skip(url)
            continue
        body = _plain(job.get("description")) or _plain(re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S))
        results.append({"title": title, "url": url, "section": "WeLoveProduct",
                        "text": f"{title}\n\n{body}"[:5000], "posted": _parse_dt(job.get("datePosted"))})
        time.sleep(1)
    log(f"  Found {len(results)} new on WeLoveProduct")
    return results


_LI_OK = re.compile(r"(worldwide|anywhere|global|europe|emea|ukrain|mena|middle east|\beu\b|remote" + criteria.EXTRA_REGIONS_ALT + ")", re.I)
_LI_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def _li_get(url: str):
    """GET for LinkedIn's public guest pages. Returns None on any block/limit — we never retry
    aggressively, never log in, and never try to get around a challenge."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_LI_UA), timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        log(f"  LinkedIn answered HTTP {e.code} — skipping LinkedIn this cycle")
    except Exception as e:
        log(f"  LinkedIn fetch error: {e}")
    return None


def check_linkedin():
    """LinkedIn public guest job search (no login). Remote only, last 24h. Single-country
    listings (e.g. just 'Paris, France') are dropped — only worldwide/Europe/EMEA/Ukraine/remote."""
    log("Checking LinkedIn (public guest search)...")
    cfg = SOURCES.get("LinkedIn", {})
    keywords = cfg.get("keywords", ["product designer", "ux ui designer", "ui ux designer"])
    location = cfg.get("location", "Europe")
    existing = get_existing_urls()
    cards, seen = [], set()
    for kw in keywords:
        q = urllib.parse.urlencode({"keywords": kw, "location": location, "f_WT": "2",
                                    "f_TPR": "r86400", "start": "0"})
        page = _li_get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + q)
        if page is None:
            break   # blocked / rate-limited: stop for this cycle
        for card in re.split(r"<li>", page)[1:]:
            m = re.search(r"/jobs/view/[^\"?]*?(\d{8,})", card)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            title = _plain((re.search(r"base-search-card__title[^>]*>(.*?)</h3>", card, re.S) or [0, ""])[1])
            company = _plain((re.search(r"base-search-card__subtitle[^>]*>(.*?)</h4>", card, re.S) or [0, ""])[1])
            loc = _plain((re.search(r"job-search-card__location[^>]*>(.*?)</span>", card, re.S) or [0, ""])[1])
            dt = re.search(r'datetime="([^"]+)"', card)
            cards.append({"id": m.group(1), "title": title, "company": company, "loc": loc,
                          "posted": _parse_dt(dt.group(1)) if dt else None})
        time.sleep(3)

    results = []
    for c in cards:
        link = f"https://www.linkedin.com/jobs/view/{c['id']}"
        if link in existing or not c["title"] or not is_relevant(c["title"]):
            continue
        if not (_LI_OK.search(c["loc"]) and _region_ok(c["loc"])):
            continue
        if len(results) >= 10:
            break   # keep detail fetches (and AI calls) modest
        detail = _li_get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{c['id']}")
        time.sleep(2)
        if not detail:
            continue
        body = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', detail, re.S)
        desc = _plain(body.group(1)) if body else ""
        if len(desc) < 200:
            continue   # nothing real to score
        text = f"{c['title']}\nCompany: {c['company']}\nLocation: {c['loc']}\n\n{desc}"[:5000]
        results.append({"title": f"{c['title']} — {c['company']}" if c["company"] else c["title"],
                        "url": link, "section": "LinkedIn", "text": text, "posted": c["posted"]})
    log(f"  Found {len(results)} new on LinkedIn")
    return results


# ============================================================
# ANALYSIS & MD FILE MANAGEMENT
# ============================================================

def add_vacancy_to_md(section_name: str, title: str, url: str, posted=None) -> None:
    """Add a new vacancy line to the appropriate section in vacancies.md."""
    with open(MD_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Deduplication guard: skip if URL already exists anywhere in the file
    if url in content:
        log(f"    Skipping duplicate URL: {url}")
        return

    lines = content.split("\n")
    lines = [l + "\n" for l in lines]
    if lines:
        lines[-1] = lines[-1].rstrip("\n") + ("\n" if content.endswith("\n") else "")

    # Use the real posting date when the source gives one, so "newest" sorting is honest.
    today = (posted or datetime.now()).strftime("%d.%m")
    new_line = f"- [{title}]({url}) *({today})*\n"

    # Find the section
    in_section = False
    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip() == f"## {section_name}":
            in_section = True
            continue
        if in_section:
            if line.startswith("## ") or line.startswith("---"):
                insert_idx = i
                break
            if line.startswith("- ["):
                insert_idx = i + 1

    if insert_idx:
        lines.insert(insert_idx, new_line)
    else:
        # Section doesn't exist — create it before "---" separator or at end
        separator_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "---" and i > 5:
                separator_idx = i
                break

        new_section = f"\n## {section_name}\n\n{new_line}\n"
        if separator_idx:
            lines.insert(separator_idx, new_section)
        else:
            lines.append(new_section)

    with open(MD_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    update_date()


def update_date():
    with open(MD_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    today = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r"Оновлено: \d{4}-\d{2}-\d{2}", f"Оновлено: {today}", content)
    with open(MD_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def analyze_vacancy(title: str, url: str, text: str | None = None) -> dict | None:
    """Analyze vacancy with Groq API. `text` = description already pulled from the source."""
    try:
        from analyze_new import fetch_page, analyze_with_groq, GROQ_KEY
        if not GROQ_KEY:
            return None
        profile_path = os.path.join(BASE_DIR, "profile.md")
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = f.read()
        page_text = text or fetch_page(url)
        return analyze_with_groq(title, url, page_text, profile)
    except Exception as e:
        log(f"  Analysis error: {e}")
        return None


CHECKERS = [
    ("Djinni", check_djinni),
    ("DOU", check_dou),
    ("Work.ua", check_workua),
    ("Wellfound", check_wellfound),
    ("Remotive", check_remotive),
    ("RemoteOK", check_remoteok),
    ("WeWorkRemotely", check_wwr),
    ("LinkedIn", check_linkedin),
    ("UIUXJobsBoard", check_uiux),
    ("EUremoteJobs", check_euremotejobs),
    ("Workable", check_workable),
    ("Layers", check_layers),
    ("TechTree", check_techtree),
    ("RemoteJobsOrg", check_remotejobs_org),
    ("NoFluffJobs", check_nofluff),
    ("WeLoveProduct", check_weloveproduct),
]
STATE_FILE = os.path.join(BASE_DIR, "source_state.json")


def load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def main():
    log("=" * 50)
    log("Starting vacancy check across all sources")
    log("=" * 50)

    # Run enabled checkers (config.SOURCES), honoring each source's min_interval_hours
    all_new = []
    checkers = []
    state = load_state()
    for name, fn in CHECKERS:
        cfg = SOURCES.get(name, {})
        if not cfg.get("enabled", True):
            continue
        wait_h = cfg.get("min_interval_hours", 0)
        if wait_h and time.time() - state.get(name, 0) < wait_h * 3600:
            log(f"Skipping {name} (checked less than {wait_h}h ago)")
            continue
        checkers.append(fn)
        try:
            all_new.extend(fn())
            state[name] = time.time()
            time.sleep(2)  # Be polite between requests
        except Exception as e:
            log(f"  ERROR in {fn.__name__}: {e}")
    save_state(state)

    # Deduplicate by URL
    seen = set()
    unique = []
    for v in all_new:
        if v["url"] not in seen:
            seen.add(v["url"])
            unique.append(v)
    all_new = unique

    # The six rules (criteria.py): remote, titles, not US-only, no relocation, no gaming/gambling.
    # Rejected vacancies are remembered in analyses.json so they are not fetched again.
    rejected_analyses = {}
    passed = []
    for v in all_new:
        ok, why = criteria.evaluate(v["title"], v.get("text") or v.get("teaser") or "",
                                    v.get("location", ""), v.get("remote_hint"))
        if ok:
            passed.append(v)
        else:
            log(f"  Rejected [{v['section']}] {v['title']} — {why}")
            rejected_analyses[v["url"]] = {"score": 1, "status": "rejected",
                                           "summary": f"Не підходить за вашими критеріями: {why}"}
    if rejected_analyses:
        stored = {}
        if os.path.exists(ANALYSES_FILE):
            with open(ANALYSES_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
        stored.update({k: v for k, v in rejected_analyses.items() if k not in stored})
        with open(ANALYSES_FILE, "w", encoding="utf-8") as f:
            json.dump(stored, f, ensure_ascii=False, indent=2)
    all_new = passed

    # Round-robin across sources so the per-run cap can't be eaten by whichever source
    # happens to come first (otherwise the foreign boards starve behind the Ukrainian ones).
    by_section = {}
    for v in all_new:
        by_section.setdefault(v["section"], []).append(v)
    all_new = [v for group in zip_longest(*by_section.values()) for v in group if v]

    if not all_new:
        log(f"No new vacancies found across {len(checkers)} sources.")
        return

    # Limit per run to avoid rate limits (Groq free: ~30 RPM)
    MAX_PER_RUN = 25
    if len(all_new) > MAX_PER_RUN:
        log(f"\nTotal: {len(all_new)} new, processing first {MAX_PER_RUN} (rest next run).\n")
        all_new = all_new[:MAX_PER_RUN]
    else:
        log(f"\nTotal: {len(all_new)} new vacancies to process.\n")

    # Load analyses
    analyses = {}
    if os.path.exists(ANALYSES_FILE):
        with open(ANALYSES_FILE, "r", encoding="utf-8") as f:
            analyses = json.load(f)

    added = 0
    for v in all_new:
        log(f"  [{v['section']}] {v['title']}")

        # Analyze before adding
        result = analyze_vacancy(v["title"], v["url"], v.get("text"))
        if result:
            analyses[v["url"]] = result
            score = result.get('score', '?')
            log(f"    Score: {score}/10")

            # Skip very low scores (1-2) — don't clutter the list.
            if isinstance(score, int) and score <= 2:
                log(f"    Skipping (score too low)")
                continue

        # Add to MD file
        add_vacancy_to_md(v["section"], v["title"], v["url"], v.get("posted"))
        added += 1

        # Rate limit for Groq free tier (30 RPM)
        time.sleep(6)

    # Save analyses
    with open(ANALYSES_FILE, "w", encoding="utf-8") as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)

    log(f"\nDone. Added {added} vacancies (skipped {len(all_new) - added} low-score).")
    log("=" * 50)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Cloud watcher for DOU: runs on GitHub Actions every 10 minutes, so it works while the laptop is off.
(DOU blocks Cloudflare servers, but GitHub's runners are allowed through.)

Same six rules as the laptop version (criteria.py is a copy of ../criteria.py).
State lives in seen.json (committed back by the workflow). First run only fills seen.json.
Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import criteria

SEARCHES = ["Senior Product designer", "Middle Product designer", "Product designer", "UX/UI Designer",
            "Middle UX/UI Designer", "Senior UX/UI Designer", "UX Designer", "Design Engineer"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
SEEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")
TOKEN, CHAT = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")


def plain(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def scan():
    jobs, errors = {}, 0
    for term in SEARCHES:
        try:
            page = get("https://jobs.dou.ua/vacancies/?" + urllib.parse.urlencode({"search": term}))
        except Exception as e:
            errors += 1
            print(f"fetch failed ({term}): {e}")
            continue
        for card in re.findall(r'<li class="l-vacancy[^"]*">(.*?)</li>', page, re.S):
            m = re.search(r'<a class="vt" href="(https://jobs\.dou\.ua/companies/[^/]+/vacancies/\d+/)[^"]*"\s*>(.*?)</a>',
                          card, re.S)
            if not m or m.group(1) in jobs:
                continue
            url, title = m.group(1), plain(m.group(2))
            field = lambda pat: plain((re.search(pat, card, re.S) or [0, ""])[1])
            company = field(r'class="company"[^>]*>(.*?)</a>')
            cities = field(r'class="cities[^"]*">(.*?)</span>')
            salary = field(r'class="salary">(.*?)</span>')
            info = field(r'class="sh-info">(.*?)</div>')
            ok, why = criteria.evaluate(title, f"{title}\nCompany: {company}\nLocation: {cities}\n{info}", cities, None)
            if not ok:
                print(f"rejected: {title} — {why}")
                continue
            jobs[url] = {"title": f"{title} — {company}" if company else title, "url": url,
                         "extra": " · ".join(x for x in (salary, cities) if x)}
        time.sleep(1)
    return jobs, errors


def send(text):
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data), timeout=20)
        return True
    except Exception as e:
        print("telegram failed:", e)
        return False


def main():
    jobs, errors = scan()
    print(f"found {len(jobs)} matching, {errors} fetch errors")
    if errors == len(SEARCHES):
        print("DOU did not answer at all")
        return 1
    first = not os.path.exists(SEEN)
    seen = {} if first else json.load(open(SEEN))
    now = int(time.time())
    fresh = [j for u, j in jobs.items() if u not in seen]
    sent = 0
    for j in reversed(fresh):   # oldest first
        if first:
            seen[j["url"]] = now
            continue
        lines = [f'🆕 <a href="{html.escape(j["url"], quote=True)}">{html.escape(j["title"])}</a>']
        if j["extra"]:
            lines.append(html.escape(j["extra"]))
        lines.append("<i>DOU</i>")
        if send("\n".join(lines)):
            seen[j["url"]] = now
            sent += 1
            time.sleep(0.5)
    if first and TOKEN and CHAT:
        send(f"☁️ Сторож DOU тепер працює в хмарі: нові вакансії приходитимуть, навіть коли ноутбук вимкнений. "
             f"Зараз під ваші правила підходить {len(jobs)}, їх я вже не надсилаю.")
    for u in [u for u, t in seen.items() if now - t > 90 * 86400]:
        del seen[u]
    json.dump(seen, open(SEEN, "w"), ensure_ascii=False, indent=0)
    print(f"new {len(fresh)}, sent {sent}{' (seeded)' if first else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

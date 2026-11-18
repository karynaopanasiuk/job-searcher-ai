#!/usr/bin/env python3
"""
Cloud watcher for all other boards (everything except DOU and Djinni, which have their own watchers).
Runs on GitHub Actions every 10 minutes, so it works while the laptop is off.

It reuses the laptop's checkers (check_new.py), the same config (config.py) and the same six rules
(criteria.py). No AI scoring here: a vacancy that passes the rules goes straight to Telegram.
State: boards_seen.json, skipped.json, source_state.json (committed back by the workflow).
First run only fills the state and posts one summary message.
Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
"""
import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import check_new as cn   # noqa: E402
import criteria          # noqa: E402

SEEN = os.path.join(ROOT, "boards_seen.json")
TOKEN, CHAT = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
MAX_SEND = 15
OWN_WATCHERS = ("Djinni", "DOU", "EUremoteJobs")   # DOU, Djinni: own watchers; EU Remote Jobs refuses cloud servers (laptop only)
NAMES = {"UIUXJobsBoard": "UIUX Jobs Board", "EURemoteJobs": "EU Remote Jobs", "WeWorkRemotely": "We Work Remotely",
         "RemoteJobsOrg": "remotejobs.org", "NoFluffJobs": "No Fluff Jobs", "WeLoveProduct": "WeLoveProduct"}

# Point the shared code at this repo's own state files
cn.STATE_FILE = os.path.join(ROOT, "source_state.json")
cn.SKIPPED_FILE = os.path.join(ROOT, "skipped.json")
_seen = {}
cn.get_existing_urls = lambda: set(_seen) | cn._load_skipped()


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
    global _seen
    first = not os.path.exists(SEEN)
    _seen = {} if first else json.load(open(SEEN))
    state = cn.load_state()
    found, errors, ran = [], 0, 0
    for name, fn in cn.CHECKERS:
        cfg = cn.SOURCES.get(name, {})
        if name in OWN_WATCHERS or not cfg.get("enabled", True):
            continue
        wait_h = cfg.get("min_interval_hours", 0)
        if wait_h and time.time() - state.get(name, 0) < wait_h * 3600:
            print(f"skip {name}: checked less than {wait_h}h ago")
            continue
        ran += 1
        try:
            found.extend(fn())
            state[name] = time.time()
        except Exception as e:
            errors += 1
            print(f"ERROR in {name}: {e}")
        time.sleep(2)
    cn.save_state(state)

    uniq = {}
    for v in found:
        uniq.setdefault(v["url"], v)
    now = int(time.time())
    to_send = []
    for url, v in sorted(uniq.items(), key=lambda kv: kv[1].get("posted") or cn.datetime.min):
        ok, why = criteria.evaluate(v["title"], v.get("text") or "", v.get("location", ""), v.get("remote_hint"))
        if not ok:
            print(f"rejected [{v['section']}] {v['title']} — {why}")
            _seen[url] = now
        elif first:
            _seen[url] = now
        else:
            to_send.append(v)

    sent = 0
    for v in to_send[:MAX_SEND]:
        lines = [f'🆕 <a href="{html.escape(v["url"], quote=True)}">{html.escape(v["title"])}</a>']
        loc = (v.get("location") or "").strip()
        if loc:
            lines.append(html.escape(loc[:120]))
        lines.append(f"<i>{html.escape(NAMES.get(v['section'], v['section']))}</i>")
        if send("\n".join(lines)):
            _seen[v["url"]] = now
            sent += 1
            time.sleep(0.5)
    rest = to_send[MAX_SEND:]
    if rest and send(f"…і ще {len(rest)} нових вакансій з інших платформ (дивіться дашборд)."):
        for v in rest:
            _seen[v["url"]] = now
    if first and TOKEN and CHAT:
        send(f"☁️ Інші платформи (UIUX Jobs Board, Workable, EU Remote Jobs, Remotive, Layers, TechTree, "
             f"remotejobs.org, NoFluffJobs, WeLoveProduct, We Work Remotely) тепер перевіряються в хмарі. "
             f"Зараз під ваші правила підходить {sum(1 for v in uniq.values() if criteria.evaluate(v['title'], v.get('text') or '', v.get('location', ''), v.get('remote_hint'))[0])}, їх я вже не надсилаю.")
    for u in [u for u, t in _seen.items() if now - t > 90 * 86400]:
        del _seen[u]
    json.dump({cn.criteria.mask(k): v for k, v in _seen.items()}, open(SEEN, "w"), ensure_ascii=False, indent=0)
    print(f"checked {ran} sources ({errors} failed), found {len(found)}, sent {sent}"
          f"{' (seeded)' if first else ''}")
    return 1 if ran and errors == ran else 0


if __name__ == "__main__":
    sys.exit(main())

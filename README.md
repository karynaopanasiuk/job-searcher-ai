# job-searcher-ai

A personal job-search assistant for product designers. It checks job boards around the clock, keeps only the
vacancies that pass six plain rules, and sends each new one to Telegram within about ten minutes of it appearing.

This repository is the **cloud part**: it runs on GitHub Actions, so it keeps working when my laptop is off.

## How it works

```
every 10 minutes (GitHub Actions)
  -> read the board (HTML, RSS or JSON)
  -> skip anything already seen (state is committed back to this repo)
  -> open each new vacancy and run the six rules in code (criteria.py)
  -> send the ones that pass to Telegram: title, link, board name
```

The rules are plain code, not an AI guess, so the result is the same every time and easy to change.
Every rule has one place in `criteria.py`.

## The six rules

1. **Remote only.** Office and hybrid roles are dropped.
2. **Title must match.** Senior / Middle Product designer, Product designer, UX/UI Designer, UX Designer,
   Design Engineer. Junior and intern titles are dropped. Hardware "design engineer" roles (chips, mechanical)
   are dropped too.
3. **Not US-only.** "US residents only", "must be authorised to work in the US" and similar are dropped.
4. **No relocation.**
5. **Years of experience are not a filter.**
6. **No gaming or gambling.**

## Platforms

| Platform | How it is read | Where it runs |
|---|---|---|
| DOU | HTML | GitHub Actions (`watch_dou.py`) |
| UIUX Jobs Board | region pages, JSON-LD | GitHub Actions (`watch_boards.py`) |
| Workable | public job pages | GitHub Actions |
| Layers | HTML | GitHub Actions |
| TechTree | HTML | GitHub Actions |
| remotejobs.org | HTML | GitHub Actions |
| No Fluff Jobs | HTML | GitHub Actions |
| WeLoveProduct | HTML | GitHub Actions |
| Remotive | public API | GitHub Actions |
| We Work Remotely | RSS | GitHub Actions |
| Djinni | HTML | a separate Cloudflare Worker (not in this repo) |
| EU Remote Jobs | needs a real browser | runs on my laptop only |

Not covered: Indeed, Glassdoor and Startup Jobs. They sit behind a bot check, and I do not try to get around it.

## Files

- `criteria.py` — the six rules. Edit the lists at the top to change them.
- `check_new.py` — one checker per platform, plus the shared filtering.
- `config.py` — titles to search for, which platforms are on, how often each is read.
- `watch_dou.py`, `watch_boards.py` — the entry points the workflows run.
- `.github/workflows/` — two workflows, both on a 10-minute schedule.
- `seen.json`, `boards_seen.json`, `skipped.json`, `source_state.json` — what has already been seen.
  The workflows commit them back, so the next run knows where to continue.

## Run your own copy

1. Fork the repository.
2. In **Settings → Secrets and variables → Actions**, add two secrets:
   `TELEGRAM_BOT_TOKEN` (from @BotFather) and `TELEGRAM_CHAT_ID`.
3. Change `TITLES` and the platforms in `config.py`, and the rules in `criteria.py`.
4. Enable the workflows in the **Actions** tab. The first run saves what it finds without sending
   anything, then sends one summary message. After that you only get new vacancies.

Optional: set the repository variable `EXTRA_REGIONS` (for example a country name) to count that region as open
to you, and `UIUX_EXTRA_PAGES` to read one more UIUX Jobs Board region page.

## Notes

- No secrets are stored in the code. Tokens live in GitHub Actions secrets.
- GitHub pauses scheduled workflows after 60 days without repository activity. The state commits count as
  activity, so this should not happen while the watchers are running.
- Please check each platform's terms before reading it automatically. The watchers are gentle: one request per
  page, no login, no bot-check bypass.

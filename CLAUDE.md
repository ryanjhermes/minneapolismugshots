# CLAUDE.md

Developer guide for this repo, for Claude Code and for Ryan. The public-facing overview is `README.md`.

## Overview

A hands-off pipeline that runs entirely on GitHub Actions. Every night it scrapes the Hennepin County Jail Roster,
ranks the day's bookings and queues the top 10. It then posts one mugshot Reel per peak-hour slot to
[@minneapolismugshots](https://instagram.com/minneapolismugshots). It also queues mugshots from Bring Me The News
crime stories, posts one news story a day, and handles removal requests sent by DM.

**Status (Oct 2026):** scraping, ranking, Reels and posting have been live for months. Three newer features are
**not yet proven in production**: the news post (`news.py`), Bring Me The News mugshots (`bmtn.py`), and DM handling
(`dms.py`, scheduled runs are off until the `DM_ENABLED` repo variable is set). All three have dry-run modes, so use them.

## Layout

```
bot/                  All Python code, run as `python -m bot <command>` from the repo root
  __main__.py         CLI: one subcommand per job (see Commands)
  config.py           Every tunable: schedule, thresholds, file paths, URLs. Change behavior here
  common.py           Central-time clock, JSON load/save, file delete, GitHub step outputs
  scraper.py          Selenium scrape: search form, booking modals (FieldExtractor), CSV
  ranking.py          Queue order: charge, then CLIP distinctiveness + severity bonus, then bail
  clip_model.py       CLIP prompts and scores (distinctiveness; is-this-a-mugshot for bmtn)
  posting_queue.py    posting_queue.json: build, insert, next, mark posted, mugshot cleanup
  posting.py          preflight (should this hour post?), captions, post_next
  instagram.py        Meta Graph API: create container, wait for processing, publish
  reels.py            ffmpeg 9:16 Reels for the unposted queue
  bmtn.py             Bring Me The News RSS: queue stories whose lead image is a mugshot
  news.py             Daily news post: score the same feed with a zero-shot model, post the top story
  dms.py              Instagram DMs: delete posts on request, reply, hand off everything else
  removals.py         removed.json (hashed names) and purging those people everywhere
.github/workflows/    The schedule (see Workflows)
build_pages.sh        Builds the GitHub Pages site into docs/ (mugshots, CSV, Reels)
mugshots/             Images for queued posts (committed, so Pages can serve them)
posting_queue.json    Queue state; see the docstring in bot/posting_queue.py for its shape
jail_roster_data.csv  Last night's scrape
news_state.json       Plus bmtn_state.json, dm_state.json, removed.json once those jobs have run
```

## Commands

```bash
pip install -r requirements.txt               # Scraper deps
pip install torch transformers pillow         # CLIP / news / bmtn models (CI pins transformers<5)

python -m bot --help                          # All commands
python -m bot scrape [--test]                 # Scrape 100 bookings (25 with --test), write CSV + mugshots, rebuild queue
python -m bot preflight                       # Would this hour post? Prints mode= / reason=
python -m bot post-next [--dry-run]           # Post the next queued entry (Reel, falling back to image)
python -m bot make-reels                      # Render Reels for the unposted queue into reels/ (needs ffmpeg)
python -m bot check-queue                     # Queue status
python -m bot cleanup-posted                  # Delete mugshots of posted entries
python -m bot purge-unqueued                  # Delete every mugshot no upcoming post needs
python -m bot purge-removed                   # Strip people on the removal list from CSV, queue, mugshots/
python -m bot bmtn [--check | --dry-run]      # Queue Bring Me The News mugshots
python -m bot news [--dry-run | --force]      # Daily news post (--force skips the 6 PM / once-a-day checks)
python -m bot dms [--dry-run | --check-token] # Handle removal requests in DMs
./build_pages.sh                              # Build the Pages site into docs/
```

**Local runs edit the real state files.** `scrape`, `post-next`, `bmtn`, `purge-*` and `make-reels` rewrite
`posting_queue.json`, the CSV and `mugshots/`, and the next workflow run pulls from `main` and overwrites them anyway.
To try a change, run it in a scratch copy of the repo, or use the `--dry-run` / `--check` flags, which write nothing.
With a real `.env`, only `post-next` without `--dry-run`, `news --force` and `dms` without `--dry-run` reach Instagram.

## How a day runs (Central time)

```
11 PM   daily-scrape   scrape → CSV + mugshots/ → rank → posting_queue.json (top 10) → Reels → Pages
hourly  bmtn-check     new Bring Me The News mugshot stories → front of the queue → Reels → Pages
7,9,11,12,1,5,7,8      instagram-posting posts one queued entry per slot (Reel via its Pages URL)
6 PM    news-posting   best new crime story → one image post (feed image URL, no Pages)
hourly  dm-check       removal requests → delete post, add to removed.json → purge + redeploy Pages
```

**Why GitHub Pages?** The Graph API only accepts media by public URL. Mugshots are committed and served from
`ryanjhermes.github.io/minneapolismugshots/mugshots/`; Reels are rendered on the runner and exist only in the Pages
artifact (`reels/` is gitignored).

## Workflows

| Workflow | When | Runs | Commits | Installs |
|---|---|---|---|---|
| `daily-scrape.yml` | 04:00 UTC (11 PM CDT), manual | `scrape`, `purge-removed`, `purge-unqueued`, `make-reels`, Pages | everything (`git add .`) | Chrome, ffmpeg, `requirements.txt`, torch, transformers |
| `instagram-posting.yml` | :07 hourly, 12–03 UTC | `preflight`, then `post-next` + `cleanup-posted` | queue, mugshots/ | requests, dotenv, pytz |
| `bmtn-check.yml` | :45 hourly, manual (dry run default) | `bmtn --check`, then `bmtn` + `make-reels` + Pages if new | queue, mugshots/, bmtn_state | pillow; torch, transformers<5 and ffmpeg only if new |
| `news-posting.yml` | 23:15 and 00:15 UTC, manual (dry run default) | `news` | news_state | pillow, torch, transformers<5 |
| `dm-check.yml` | :37 hourly if `DM_ENABLED`, manual (dry run default) | `dms`; on deletes `purge-removed`, `make-reels`, Pages | dm_state, removed; then CSV, queue, mugshots/ | requests, dotenv, pytz (+ ffmpeg for the purge job) |
| `rebuild-reels.yml` | manual | `make-reels`, Pages | queue | ffmpeg, requests, dotenv, pytz |

- Everything that edits the queue shares the `queue-state` concurrency group, so they never run at the same time.
- Every workflow checks out `ref: main` (not the triggering commit) and retries `git push` after a `pull --rebase`.
  The bots commit to `main` many times a day, so **`git pull --rebase` before you push**.
- Each workflow installs only its own dependencies. That's why `bot/__main__.py` imports each command's module
  lazily and why `config.py` must stay free of heavy imports. If you add an import to a shared module
  (`config`, `common`, `removals`, `posting_queue`), check it against the narrowest install above (requests,
  python-dotenv, pytz).

## Rules the code depends on

- **Captions**: every mugshot caption has a `NAME: LAST, FIRST MIDDLE` line. `dms.load_posts` finds posts by that
  line, so don't change its format.
- **Posting slots** (`posting.preflight`): a scheduled run posts if nothing has posted since the latest
  `config.POSTING_HOURS` slot started. Late GitHub runs still post, and missed slots don't stack into a burst.
- **Queue rebuilds** (`posting_queue.build`) keep entries posted in the last 24h (so slot timing and "already posted"
  survive) and unposted Bring Me The News entries (which stay ahead of the night's inmates).
- **Removals** (`removed.json`) hold SHA-256 hashes of names, so the public repo doesn't list who asked. The scrape,
  posting and bmtn all skip anyone on the list; `purge-removed` scrubs them from committed files. A removed person's
  posted queue entry keeps its `posted_at` with empty `data`.
- **Pages is replaced wholesale** on every deploy, so any workflow that deploys Pages renders Reels for the whole
  queue first. Otherwise queued Reel URLs would 404.
- **Ranking**: has a charge, then distinctiveness (CLIP, rescaled 0..1 within the batch) + `config.SEVERITY_BONUS`,
  then bail amount. Edit `DISTINCTIVE_PROMPTS` / `PLAIN_PROMPTS` in `clip_model.py` to change what "stands out"
  means. If torch or the model fails, distinctiveness is 0 and ranking still works.

## Known gotchas (don't rediscover these)

- **Headless Chrome window size**: the default 800x600 renders the booking modal in a narrow layout where charges
  never appear. `scraper.open_browser` sets 1920x1080 in CI.
- **Charges load late** in the modal: `FieldExtractor._wait_for_charges` waits for `Charge: 1` + `Description:`,
  scrolls, retries, then falls back to reading the DOM, but only if the modal shows the same name (a stale modal
  once attached the wrong person's charge). A failed charge read logs a 1,500-character modal sample for debugging.
- **CBS Minnesota returns HTTP 406** to GitHub runners, so news uses the Bring Me The News feed. Its tag pages are
  behind bot protection; the RSS feed (`config.BMTN_FEED_URL`) is not.
- **transformers 5 removed** the `question-answering` and `zero-shot-classification` pipelines that bmtn and news use.
  Their workflows pin `transformers<5`; the scrape workflow only needs CLIP and allows <6.
- **Bring Me The News feed images** (`?profile=rss`) are a 16:9 crop that cuts mugshots off at the chin, so
  `bmtn.fetch_items` drops the query string to get the full image (Oct 12). Its captions open with as many whole story
  paragraphs as fit Instagram's 2,200-character limit (`Story`, from `content:encoded`; `posting.fit_story`).
- **Instagram processes media asynchronously.** Publishing before `status_code == FINISHED` fails with
  "Media ID is not available", so `instagram.post` polls first (up to 5 min for Reels).
- **Reel text placement** keeps clear of Instagram's UI (top bar, right-side buttons, bottom caption); see the
  constants in `reels.py`.

## Environment variables (`.env`, never committed)

```
ACCESS_TOKEN=   # Meta Graph API long-lived token (scopes: dms.NEEDED_SCOPES)
APP_ID=         # Meta App ID
BUSINESS_ID=    # Instagram Business Account ID
```

In CI these come from the secrets `META_ACCESS_TOKEN`, `META_APP_ID` and `META_BUSINESS_ID`.
`python -m bot dms --check-token` lists the scopes the token is missing and when it expires.

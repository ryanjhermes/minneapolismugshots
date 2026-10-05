# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Automated pipeline that scrapes the Hennepin County Jail Roster daily, filters inmates by priority, and posts mugshots to Instagram. Runs entirely via GitHub Actions.

## Commands

```bash
# Setup
pip install -r requirements.txt

# Scraping
python data.py                   # Full scrape (100 inmates), builds posting queue of top 10
python data.py test              # Test scrape (25 inmates, filters to top 10 highest priority)

# Posting
python data.py post-next         # Post next inmate from queue
python data.py post-next-test    # Simulate posting without hitting the API

# Queue management
python data.py check-queue       # Inspect posting_queue.json state
python data.py check-posting-status  # Show daily post count, next allowed window
python data.py cleanup-posted    # Delete mugshot files for already-posted inmates
python data.py purge-unqueued    # Delete every mugshot not needed for an upcoming post
```

## Architecture

### Data flow

```
Scrape → jail_roster_data.csv + mugshots/
       → filter top 10 by priority → posting_queue.json
       → every 3h: Instagram API (via GitHub Pages URL)
```

**Why GitHub Pages?** Instagram's API requires a public HTTPS URL for images. Mugshots are committed to the repo and served from `ryanjhermes.github.io/minneapolismugshots/mugshots/`. The scrape workflow pushes files; the posting workflow reads them via that URL.

### Key files

| File | Role |
|------|------|
| `data.py` | Everything: scraper, queue, posting, CLI entrypoint (~2,600 lines) |
| `mugshot_ranker.py` | CLIP zero-shot distinctiveness score per mugshot |
| `chargeextraction.py` | Charge text parsing utilities |
| `posting_queue.json` | Runtime state — which inmates are queued/posted |
| `jail_roster_data.csv` | Cumulative scraped data |

### GitHub Actions workflows

- **`daily-scrape.yml`** — Runs at 11 PM Central (04:00 UTC). Scrapes the jail roster, writes CSV + mugshots, creates `posting_queue.json` with top 10 priority inmates, deploys to GitHub Pages.
- **`instagram-posting.yml`** — Runs every 3 hours. Preflight check (pure Python, no pip install needed) gates on: queue not empty, daily limit (8 posts), posting window (24/7), 3-hour interval since last post. If ready, posts (waits for Instagram to finish processing the image before publishing).

### Posting priority

Inmates with a charge rank first, then by visual distinctiveness, then by bail dollar amount. The top 10 go into the queue.

Distinctiveness comes from `mugshot_ranker.py`: CLIP (`openai/clip-vit-base-patch32`, free, CPU) scores each mugshot against the prompts in `DISTINCTIVE_PROMPTS` vs `PLAIN_PROMPTS`. Edit those lists to change what "stands out" means. If torch/transformers or the model download fails, every score is 0 and ranking falls back to charge + bail. Local setup: `pip install torch transformers pillow`.

### Environment variables (`.env`)

```
ACCESS_TOKEN=   # Meta Graph API long-lived access token
APP_ID=         # Meta App ID
BUSINESS_ID=    # Instagram Business Account ID
```

In CI these come from GitHub Secrets (`META_ACCESS_TOKEN`, `META_APP_ID`, `META_BUSINESS_ID`).

### `Config` class

All magic numbers live in `data.py:Config` — posting limits, intervals, file paths, CSS selectors, URL. Change behavior there rather than hunting through functions.

### Scraping

Uses Selenium + Chrome. `FieldExtractor` class opens each booking modal and parses name, charge, bail, and mugshot from page text using `Config.NAME_PATTERNS` and related lists. Mugshots are saved as `mugshots/mugshot_LASTNAME_FIRSTNAME_MIDDLENAME.jpg`.

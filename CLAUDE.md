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
python data.py post-next         # Post next inmate from queue with BLIP filtering
python data.py post-next-test    # Simulate posting without hitting the API

# Queue management
python data.py check-queue       # Inspect posting_queue.json state
python data.py check-posting-status  # Show daily post count, next allowed window
python data.py cleanup-posted    # Delete mugshot files for already-posted inmates

# AI filter
python data.py test-ai-filter    # Run BLIP filter against a sample mugshot
```

Test files can be run directly:
```bash
python test_ai_filter.py
python test_blip_availability.py
python test_blip_filter.py
python test_multiple_mugshots.py
```

## Architecture

### Data flow

```
Scrape → jail_roster_data.csv + mugshots/
       → filter top 10 by priority → posting_queue.json
       → every 3h: BLIP filter → Instagram API (via GitHub Pages URL)
```

**Why GitHub Pages?** Instagram's API requires a public HTTPS URL for images. Mugshots are committed to the repo and served from `ryanjhermes.github.io/minneapolismugshots/mugshots/`. The scrape workflow pushes files; the posting workflow reads them via that URL.

### Key files

| File | Role |
|------|------|
| `data.py` | Everything: scraper, queue, posting, CLI entrypoint (~2,600 lines) |
| `openai_filter.py` | BLIP VQA image filter (name is historical — does **not** use OpenAI) |
| `chargeextraction.py` | Charge text parsing utilities |
| `posting_queue.json` | Runtime state — which inmates are queued/posted |
| `jail_roster_data.csv` | Cumulative scraped data |

### GitHub Actions workflows

- **`daily-scrape.yml`** — Runs at 11 PM Central (04:00 UTC). Scrapes the jail roster, writes CSV + mugshots, creates `posting_queue.json` with top 10 priority inmates, deploys to GitHub Pages.
- **`instagram-posting.yml`** — Runs every 3 hours. Preflight check (pure Python, no pip install needed) gates on: queue not empty, daily limit (8 posts), posting window (24/7), 3-hour interval since last post. If ready, runs BLIP filter and posts.

### Posting priority

Inmates are ranked: "Hold Without Bail" first, then by bail dollar amount descending. Only inmates with both a mugshot and charge are eligible. The top 10 go into the queue.

### BLIP filter (`BLIPImageFilter` in `openai_filter.py`)

Two-step decision tree using `Salesforce/blip-vqa-base`:
1. "Does the person look disheveled / history of violence / extreme drug use?" → approve if yes/strong_yes
2. "Is the person conventionally attractive?" → approve if yes/strong_yes  
3. Otherwise reject

Falls back to **approve** on any error (so a missing model doesn't block all posts). `OpenAIImageFilter` is a backward-compat alias for the same class.

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

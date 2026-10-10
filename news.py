"""Daily news post: pick the most outlandish new story on CBS Minnesota's crime page and
post its thumbnail, headline, description and link to Instagram.

Free and local: stories are scored with a zero-shot NLI model
(MoritzLaurer/deberta-v3-base-zeroshot-v2.0, ~700 MB, MIT) on the GitHub Actions CPU.

python news.py --dry-run   # Show scores and what would post, change nothing
python news.py             # Post the top story if it clears Config.NEWS_MIN_SCORE (6 PM Central only)
python news.py --force     # Post now, ignoring the time-of-day and once-per-day checks
"""
import html
import json
import re
import sys
from datetime import datetime, timedelta

import pytz
import requests

from data import Config, get_api_credentials, post_to_instagram

MODEL_NAME = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"
STATE_FILE = "news_state.json"
CENTRAL = pytz.timezone('US/Central')

# Edit these to change what counts as "worth posting". Each label is scored on its own
# (0..1, "is this story X?") and a story's score is its strongest label
INTERESTING_LABELS = [
    "bizarre or weird",
    "funny or absurd",
    "shocking or extreme",
    "outlandish behavior",
    "unbelievable",
    "gross or disgusting",
    "embarrassing",
]


def fetch_stories():
    """Story cards on the crime page: [{url, title, description, image, date}]"""
    page = requests.get(Config.NEWS_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30).text
    stories = []
    for card in re.findall(r'<article[^>]*class="item[^"]*"[^>]*>(.*?)</article>', page, re.S):
        url = re.search(r'href="(https://www\.cbsnews\.com/minnesota/[^"]+)"', card)
        title = re.search(r'class="item__hed[^"]*">(.*?)</h', card, re.S)
        desc = re.search(r'class="item__dek[^"]*">(.*?)</p>', card, re.S)
        # Last JPEG is the srcset's 2x (1280x720); Instagram needs a public JPEG URL
        images = re.findall(r'(https://assets\d?\.cbsnewsstatic\.com/\S+?\.jpg)', card)
        date = re.search(r'class="item__date">(.*?)<', card)
        if not (url and title and images):
            continue
        stories.append({
            'url': url.group(1),
            'title': html.unescape(title.group(1).strip()),
            'description': html.unescape(desc.group(1).strip()) if desc else '',
            'image': images[-1],
            'date': date.group(1).strip() if date else '',
        })
    return stories


def is_recent(date_text, now):
    """Cards show '22h ago' / '5m ago' for the last day, otherwise 'Oct 9'"""
    if 'ago' in date_text:
        return True
    try:
        d = datetime.strptime(f"{date_text} {now.year}", "%b %d %Y").date()
    except ValueError:
        return False
    return now.date() - d <= timedelta(days=1)


def score_stories(stories):
    """Set story['score'] in 0..1, higher = more outlandish. Any model failure scores 0 (nothing posts)."""
    try:
        from transformers import pipeline
        classify = pipeline("zero-shot-classification", model=MODEL_NAME)
    except Exception as e:
        print(f"⚠️  Could not load {MODEL_NAME}: {e}")
        for s in stories:
            s['score'] = 0.0
        return
    # Independent scores, not a share of one total: comparing against "boring" labels let a
    # story that fit neither side (a lawmaker's DWI) outscore one that is plainly gross
    for s in stories:
        r = classify(f"{s['title']}. {s['description']}", INTERESTING_LABELS,
                     hypothesis_template="This news story is {}.", multi_label=True)
        s['score'] = max(r['scores'])


def news_caption(story):
    return f"""{story['title']}

{story['description']}

Read the full story: {story['url']}

Source: CBS News Minnesota

#Minneapolis #Minnesota #MNnews #CrimeNews #TwinCities"""


def load_state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'seen': [], 'posted': []}


def run(dry_run=False, force=False):
    now = datetime.now(CENTRAL)
    state = load_state()
    if not force and not dry_run:
        if now.hour != Config.NEWS_POSTING_HOUR:
            print(f"⏭️  Not the news hour ({now.hour}:00 Central, posts at {Config.NEWS_POSTING_HOUR}:00)")
            return
        if any(datetime.fromisoformat(p['posted_at']).astimezone(CENTRAL).date() == now.date()
               for p in state['posted']):
            print("⏭️  Already posted a news story today")
            return

    seen = set(state['seen'])
    stories = [s for s in fetch_stories() if s['url'] not in seen and is_recent(s['date'], now)]
    print(f"📰 {len(stories)} new stories")
    if not stories:
        return
    score_stories(stories)
    stories.sort(key=lambda s: s['score'], reverse=True)
    for s in stories:
        print(f"   {s['score']:.2f}  {s['title']}")

    best = stories[0]
    if best['score'] < Config.NEWS_MIN_SCORE:
        print(f"😴 Nothing outlandish enough today (best {best['score']:.2f} < {Config.NEWS_MIN_SCORE})")
        posted = False
    elif dry_run:
        print(f"🧪 DRY RUN - would post:\n   📸 {best['image']}\n{news_caption(best)}")
        return
    else:
        posted = post_to_instagram(best['image'], news_caption(best), get_api_credentials())
        if posted:
            state['posted'].append({'url': best['url'], 'title': best['title'],
                                    'score': round(best['score'], 3), 'posted_at': now.isoformat()})
    if dry_run:
        return
    # Every evaluated story is marked seen so it isn't reconsidered tomorrow; a failed post is retried next run
    state['seen'] = sorted(seen | {s['url'] for s in stories if posted or s is not best})
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    if best['score'] >= Config.NEWS_MIN_SCORE and not posted:
        sys.exit(1)


if __name__ == "__main__":
    run(dry_run='--dry-run' in sys.argv, force='--force' in sys.argv)

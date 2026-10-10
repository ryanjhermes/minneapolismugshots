"""Daily news post: pick the most outlandish new story in Bring Me The News's MN Crime feed
(the same feed bmtn.py reads) and post its lead image, headline, description and link.
CBS Minnesota was the first source, but it returns HTTP 406 to GitHub Actions runners.

Free and local: stories are scored with a zero-shot NLI model
(MoritzLaurer/deberta-v3-base-zeroshot-v2.0, ~700 MB, MIT) on the GitHub Actions CPU.

python -m bot news --dry-run   # Show scores and what would post, change nothing
python -m bot news             # Post the top story if it clears config.NEWS_MIN_SCORE (6 PM Central only)
python -m bot news --force     # Post now, ignoring the time-of-day and once-per-day checks

The post uses the feed's image URL directly (no GitHub Pages), so Instagram must accept it as a JPEG.
"""
import sys
from datetime import datetime, timedelta

from . import config, instagram
from .bmtn import fetch_items
from .common import CENTRAL, load_json, save_json

MODEL_NAME = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"

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


def fetch_stories(now):
    """Feed stories from the last day that can be news posts: [{url, title, description, image}]"""
    mugshot_posts = {i['data'].get('Source_URL') for i in load_json(config.QUEUE_FILE, {'inmates': []})['inmates']}
    items = fetch_items()
    print(f"🗂️  {len(items)} {config.BMTN_CATEGORY} stories in the feed")
    return [i for i in items
            if now - i['published'] <= timedelta(days=1)
            and i['url'] not in mugshot_posts  # already going out as a mugshot post (bmtn.py)
            and i['image'].split('?')[0].lower().endswith(('.jpg', '.jpeg'))]  # Instagram takes JPEG only


def score_stories(stories):
    """Set story['score'] in 0..1, higher = more outlandish. Any model failure scores 0 (nothing posts)."""
    try:
        from transformers import pipeline as hf_pipeline
        classify = hf_pipeline("zero-shot-classification", model=MODEL_NAME)
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

Source: Bring Me The News

#Minneapolis #Minnesota #MNnews #CrimeNews #TwinCities"""


def run(dry_run=False, force=False):
    now = datetime.now(CENTRAL)
    state = load_json(config.NEWS_STATE_FILE, {'seen': [], 'posted': []})
    if not force and not dry_run:
        if now.hour != config.NEWS_POSTING_HOUR:
            print(f"⏭️  Not the news hour ({now.hour}:00 Central, posts at {config.NEWS_POSTING_HOUR}:00)")
            return
        if any(datetime.fromisoformat(p['posted_at']).astimezone(CENTRAL).date() == now.date()
               for p in state['posted']):
            print("⏭️  Already posted a news story today")
            return

    seen = set(state['seen'])
    stories = [s for s in fetch_stories(now) if s['url'] not in seen]
    print(f"📰 {len(stories)} new stories")
    if not stories:
        return
    score_stories(stories)
    stories.sort(key=lambda s: s['score'], reverse=True)
    for s in stories:
        print(f"   {s['score']:.2f}  {s['title']}")

    best = stories[0]
    if best['score'] < config.NEWS_MIN_SCORE:
        print(f"😴 Nothing outlandish enough today (best {best['score']:.2f} < {config.NEWS_MIN_SCORE})")
        posted = False
    elif dry_run:
        print(f"🧪 DRY RUN - would post:\n   📸 {best['image']}\n{news_caption(best)}")
        return
    else:
        posted = instagram.post(best['image'], news_caption(best), instagram.credentials())
        if posted:
            state['posted'].append({'url': best['url'], 'title': best['title'],
                                    'score': round(best['score'], 3), 'posted_at': now.isoformat()})
    if dry_run:
        return
    # Every evaluated story is marked seen so it isn't reconsidered tomorrow; a failed post is retried next run
    state['seen'] = sorted(seen | {s['url'] for s in stories if posted or s is not best})
    save_json(config.NEWS_STATE_FILE, state)
    if best['score'] >= config.NEWS_MIN_SCORE and not posted:
        sys.exit(1)
